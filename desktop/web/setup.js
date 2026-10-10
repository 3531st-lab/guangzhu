// 安装版的后台准备：读配置进度，并自动替用户完成最后两步（登记工作区、读取可用模型）。不画页面、不需要用户点。
// Codex review R05: a bridge error or a reply that never comes is kept in `error` until the user retries; a retry sends each step once more.
const READ_ERROR = '无法读取准备进度，正在重试。', WAIT_MS = 60e3;
export class Setup {
  constructor(api, bridge, changed) {
    this.api = api;
    this.bridge = bridge;
    this.changed = changed;
    this.status = null;
    this.sent = new Set();
    try {this.refreshed = new Set(JSON.parse(globalThis.sessionStorage?.getItem('gz.setup.refresh') ?? '[]'));}
    catch {this.refreshed = new Set();}
    this.error = '';
    this.consumed = new Set();
    this.pending = null;
  }
  get checking() {return this.status === null;}
  get association() {return this.status?.installation;}
  get session() {
    return this.association?.installed ? {installation_id:this.association.id, workspace_id:this.status.workspace_id} : {development:true};
  }
  async poll() {
    if (this.polling) return;
    this.polling = true;
    try {
      const status = await this.api('setup/status');
      if (typeof status?.installation?.installed !== 'boolean' || !Array.isArray(status.steps) ||
          status.installation.installed && (status.required === false || !/^[a-f0-9]{64}$/.test(status.installation.id)) ||
          this.association && status.installation.id !== this.association.id) throw new Error('无法确认安装状态');
      const before = JSON.stringify([this.status, this.error]);
      this.status = status;
      if (this.error === READ_ERROR) this.error = '';
      this.bridge.installation = status.installation.installed ? status.installation.id : null;
      this.bridge.workspace = status.workspace_id;
      this.advance();
      if (this.pending && Date.now() - this.pending.at > WAIT_MS) this.error ||= this.pending.what + '，1 分钟没有回应';
      if (JSON.stringify([this.status, this.error]) !== before) this.changed();
    } catch {
      this.error = READ_ERROR;
      this.changed();
    }
    finally {this.polling = false;}
  }
  advance() {
    const s = this.status;
    if (!s?.installation.installed || !s.operation_id || !['waiting_workspace', 'waiting_models', 'ready'].includes(s.phase)) return;
    const key = s.installation.id + ':' + s.operation_id;
    if (s.phase === 'waiting_workspace' && !this.refreshed.has(key) && this.bridge.available) {
      this.refreshed.add(key);
      try {globalThis.sessionStorage?.setItem('gz.setup.refresh', JSON.stringify([...this.refreshed]));}
      catch { /* Retain this document's once-only refresh guard. */ }
      this.pending = {refresh:true, what:'AGH 重新连接', at:Date.now()};
      this.bridge.refresh();
      return;
    }
    if (!this.bridge.ready) return;
    const type = s.phase === 'waiting_workspace' ? 'gz.registerWorkspace' : 'gz.models';
    if (this.sent.has(key + ':' + type)) return;
    this.sent.add(key + ':' + type);
    this.pending = {what:type === 'gz.registerWorkspace' ? 'AGH 登记工作区' : 'AGH 读取模型清单', at:Date.now()};
    this.bridge.send(type, {operation_id:s.operation_id, installation_id:s.installation.id, path:s.installation.root,
      workspace_id:s.workspace_id, preference:this.preference ?? '', review_preference:this.reviewPreference ?? ''}, {setup:true, key, type});
  }
  async receive(message, request) {
    if (message.type === 'gz.ready') {
      if (this.pending?.refresh) this.pending = null;
      this.advance();
      return false;
    }
    if (!request?.setup) return false;
    const s = this.status, key = s?.installation.id + ':' + s?.operation_id;
    if (key !== request.key || message.operation_id !== s.operation_id || message.installation_id !== s.installation.id) return true;
    if (this.consumed.has(request.key + request.type)) return true;
    this.consumed.add(request.key + request.type);
    this.pending = null;
    if (message.type === 'gz.error') this.error = message.message || 'AGH 报错，没有说明原因';
    else if (message.type === 'gz.setup') {
      try {
        const body = request.type === 'gz.registerWorkspace' ? {workspace:message.workspace} : {metadata:message.metadata};
        const result = await this.api(request.type === 'gz.registerWorkspace' ? 'setup/complete' : 'setup/models',
          {operation_id:s.operation_id, ...body});
        if (key !== this.status.installation.id + ':' + this.status.operation_id) return true;
        this.status = result;
        this.error = '';
        if (message.metadata) this.models = message.metadata;
      } catch {this.error = '准备没完成，请在首页点重试。';}
    }
    this.changed();
    return true;
  }
  recheck() {
    this.error = '';
    this.pending = null;
    if (this.bridge.available && !this.bridge.ready && this.association?.installed) { // AGH never answered: load it again
      this.pending = {refresh:true, what:'AGH 重新连接', at:Date.now()};
      this.bridge.refresh();
    }
    const s = this.status;
    if (s) for (const type of ['gz.models', 'gz.registerWorkspace']) {
      const key = s.installation.id + ':' + s.operation_id;
      this.sent.delete(key + ':' + type);
      this.consumed.delete(key + type);
    }
    return this.poll();
  }
}
