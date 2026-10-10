// 开发版 4177、安装版 4178；以后端 /api/status 报的为准。
export let AGH_ORIGIN = 'http://127.0.0.1:4177';
export function setAghOrigin(origin) {
  if (/^http:\/\/127\.0\.0\.1:\d{2,5}$/.test(origin ?? '')) AGH_ORIGIN = origin;
}
const incoming = new Set(['gz.ready','gz.session','gz.progress','gz.approval','gz.error','gz.setup','gz.settings','gz.keySaved']);
export function acceptMessage(event,source) {
  const m = event.data;
  if (m?.type === 'gz.progress' && (!Array.isArray(m.nodes) || !['running','idle'].includes(m.op))) return null;
  return event.origin === AGH_ORIGIN && event.source === source && m?.v === 1 && typeof m.id === 'string' && incoming.has(m.type) ? m : null;
}
// The iframe element never moves or reloads when the workbench route changes.
export class Bridge {
  constructor(frame,onMessage) {
    this.frame = frame;
    this.onMessage = onMessage;
    this.ready = false;
    this.models = [];
    this.logs = [];
    this.requests = new Map();
    this.started = Date.now();
    this.sequence = 0;
    this.available = false;
    this.loaded = false;
    this.receive = event => {
      const message = acceptMessage(event,this.frame.contentWindow);
      if (!message || !this.available) return;
      if (message.type === 'gz.ready' && this.installation && message.re !== this.handshake) return;
      const logged = ['gz.setup','gz.error','gz.keySaved'].includes(message.type) ? {type:message.type,re:message.re} : message;
      this.logs.push({at:new Date().toISOString(),direction:'in',message:logged});
      if (message.type === 'gz.ready') {
        this.ready = true;
        this.models = message.models ?? [];
        this.workspaceBinding = message.workspace_binding ?? null;
        this.setTheme(this.theme);
      }
      const request = this.requests.get(message.re);
      if (['gz.setup','gz.settings','gz.keySaved'].includes(message.type) && !request) return;
      // after an install the hello comes before the workspace is known, so the binding arrives with the setup reply
      if (message.type === 'gz.setup' && /^[a-f0-9]{64}$/.test(message.workspace_binding ?? '')) this.workspaceBinding = message.workspace_binding;
      if (['gz.session','gz.error','gz.setup','gz.settings','gz.keySaved'].includes(message.type)) this.requests.delete(message.re);
      this.onMessage(message,request);
    };
    window.addEventListener('message',this.receive);
    frame.addEventListener('load',() => {
      this.ready = false;
      this.handshake = null;
      this.started = Date.now();
      this.hello();
    });
    frame.addEventListener('error',() => {if (!this.ready) this.loaded = false;});
    this.timer = setInterval(() => this.hello(),1000);
    this.hello();
  }
  setAvailable(value) {
    if (!value) {
      if (this.available) this.started = Date.now();
      this.ready = false;
      this.loaded = false;
      this.models = [];
    }
    this.available = value;
    if (value && !this.ready && !this.loaded) {
      this.loaded = true;
      this.frame.src = AGH_ORIGIN+'/';
    }
  }
  refresh() {
    this.ready = false;
    this.requests.clear();
    this.handshake = null;
    this.frame.src = AGH_ORIGIN+'/';
  }
  setTheme(theme) {
    if (!['light','dark'].includes(theme)) return;
    this.theme = theme;
    if (this.ready) this.send('gz.theme',{theme});
  }
  hello() {if (this.available && this.loaded && !this.ready) this.handshake = this.send('gz.hello',{app:'guangzhu-desktop'});}
  get fallback() {return !this.ready && Date.now()-this.started >= 15000;}
  send(type,payload = {},context) {
    const message = {v:1,type,id:'gz-'+Date.now()+'-'+(++this.sequence),...payload};
    if (type === 'gz.hello') Object.assign(message,{installation_id:this.installation ?? null,workspace_id:this.workspace ?? null});
    if (context) this.requests.set(message.id,context);
    const logged = type === 'gz.saveKey' ? {type,provider:payload.provider} : type.startsWith('gz.register') || type === 'gz.models' ? {type} : message;
    this.logs.push({at:new Date().toISOString(),direction:'out',message:logged});
    this.frame.contentWindow.postMessage(message,AGH_ORIGIN);
    return message.id;
  }
  dispose() {
    clearInterval(this.timer);
    window.removeEventListener('message',this.receive);
  }
}
