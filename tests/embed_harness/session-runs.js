// Options belong to the session acknowledged for a particular start request.
export function parseTaskBrief(brief) {
  try {
    const data = JSON.parse(brief?.match(/```json\s*\n([\s\S]*?)\n```/)?.[1]);
    return data?.brief === 'guangzhu.brief/1' ? data : null;
  } catch {return null;}
}

export class SessionRuns {
  constructor() {this.requests = new Map(); this.sessions = new Map();}
  start(requestId, run) {this.requests.set(requestId,structuredClone(run ?? {}));}
  accept(message) {
    if (this.requests.has(message.re)) {
      this.sessions.set(message.session_id,this.requests.get(message.re));
      this.requests.delete(message.re);
    }
    return this.get(message.session_id);
  }
  reject(requestId) {this.requests.delete(requestId);}
  get(sessionId) {return structuredClone(this.sessions.get(sessionId) ?? {});}
  prepareOpen(sessionId, task) {
    this.opening = task?.project?.id && task?.run ? {session_id:sessionId,project_id:task.project.id,run:structuredClone(task.run)} : null;
  }
  confirmOpen(message) {
    const pending = this.opening;
    if (!pending || pending.session_id !== message.session_id) return null;
    const projects = new Set((message.nodes ?? []).flatMap(node => {
      if (node.status !== 'completed' || !/(?:^|_)gz_(?:new_project|project_summary)$/.test(node.name ?? '')) return [];
      try {const result = JSON.parse(node.result); return result.ok && result.project_id ? [result.project_id] : [];} catch {return [];}
    }));
    if (!projects.size) return null;
    this.opening = null;
    if (projects.size !== 1 || !projects.has(pending.project_id)) return null;
    this.sessions.set(pending.session_id,pending.run);
    return {...pending,run:this.get(pending.session_id)};
  }
}

// Only a still-unedited Python-generated brief can supply display metadata on open.
export function openSession(cache, send, {sessionId,generatedBrief,currentBrief,projectId}, log = () => {}) {
  const parsed = generatedBrief && generatedBrief === currentBrief ? parseTaskBrief(generatedBrief) : null;
  const task = parsed?.project?.id === projectId ? parsed : null;
  cache.prepareOpen(sessionId,task);
  if (task) log('local',{type:'run.open-options',session_id:sessionId,project_id:projectId,run:task.run});
  send('gz.open',{session_id:sessionId});
  return cache.get(sessionId);
}
