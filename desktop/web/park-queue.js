// The server owns FIFO state; this adapter drives the existing normal session lifecycle.
export class ParkQueue {
  constructor(api, send, dispatch, restore) {
    Object.assign(this, {api, send, dispatch, restore, id:null, queue:null, busy:false});
    this.serial = Promise.resolve();
  }
  get item() { return this.queue?.items.find(item => !['completed', 'failed', 'skipped'].includes(item.status)); }
  async load(id) {
    if (this.id && id !== this.id && this.item) throw new Error('另一园区队列尚未结束，请先完成或跳过');
    this.id = id;
    this.queue = await this.api(`parks/${id}/queue`);
    return this.queue;
  }
  event(action, extra = {}) {
    const id = this.id, item = this.item?.id;
    const operation = async () => {
      if (id !== this.id || item !== this.item?.id) throw new Error('队列身份已改变，忽略旧事件');
      this.queue = await this.api(`parks/${id}/queue/${action}`, {revision:this.queue.revision, item, ...extra});
      this.changed?.();
      return this.queue;
    };
    const result = this.serial.then(operation);
    this.serial = result.catch(() => {});
    return result;
  }
  async next() {
    if (this.busy || !this.item || this.queue.paused) return;
    this.busy = true;
    try {
      if (this.item.status === 'pending') await this.event('claim');
      if (this.item.status === 'creating') await this.dispatch(this.item);
      else await this.restore(this.item);
    } catch (error) {
      if (error.recoverable) {
        await this.event('hold', {reason:error.message});
        throw error;
      }
      if (this.item?.status !== 'creating') throw error;
      await this.event('error', {reason:error.message});
    } finally { this.busy = false; }
    if (this.item?.status === 'pending') return this.next();
  }
  async opened(session) {
    const item = this.item;
    if (!item || session !== item[item.stage + '_session'] || item.status !== 'creating') return;
    const {brief} = await this.api(`parks/${this.id}/prompt`);
    if (this.item?.id !== item.id || this.item.stage !== item.stage || this.item.status !== 'creating') return;
    await this.event('sending');
    this.send('gz.parkPrompt', {session_id:session, text:brief});
  }
  async observe(message) {
    const item = this.item;
    if (!item || message.session_id !== item[item.stage + '_session']) return;
    if (message.type === 'gz.progress' && message.started && !item.started && item.status !== 'creating') await this.event('observed');
    if (item.status === 'cancelling') {
      const cancellation = message.session_id + (message.started ? ':started' : ':pending');
      if (message.type === 'gz.progress' && this.cancelling !== cancellation) {
        await this.event('cancel_requested');
        this.cancelling = cancellation;
        this.send('gz.cancel', {session_id:message.session_id});
      }
      if (message.type === 'gz.progress' && message.op === 'idle' && message.started && this.item?.cancel_requested) {
        await this.event('cancelled');
        await this.next();
      }
      return;
    }
    if (message.type === 'gz.approval' && message.pending && item.status !== 'approval') return this.event('approval');
    if (message.type === 'gz.progress' && message.started && ['sending', 'reconcile'].includes(item.status)) return this.event('running');
    if (message.type === 'gz.approval' && !message.pending && item.status === 'approval') return this.event('running');
  }
  abandon() {  // nothing is sent again; a new batch can start right after
    return this.item ? this.event('abandon') : null;
  }
  async skip() {
    await this.event('skip');
    if (this.item?.status === 'cancelling') await this.restore(this.item);
    else await this.next();
  }
}
