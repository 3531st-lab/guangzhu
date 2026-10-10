export function decode(value) {
  try {
    return typeof value === 'string' ? JSON.parse(value) : value;
  } catch {
    return null;
  }
}
export const toolName = value => value?.match(/(?:^|_)(gz_[a-z_]+|subagent_fork)$/)?.[1] ?? value;
const stable = value => JSON.stringify(value, (_, item) => item && typeof item === 'object' && !Array.isArray(item)
  ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item);
export const sameArguments = (a, b) => a != null && b != null && stable(a) === stable(b);
export function pendingLabel(value) {
  const seconds = Math.max(0, Math.floor(value?.elapsed_s ?? 0));
  const time = seconds >= 60 ? `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒` : `${seconds} 秒`;
  return `计算中 · 已用 ${time}${value?.stage ? ' · ' + value.stage : ''}`;
}
export function resolvedTools(nodes = []) {
  const rows = nodes.map((n, index) => ({...n, call_index:index, completion_index:index})).filter(n => n.kind === 'tool').map(n => ({...n,
    name:toolName(n.name),
    data:decode(n.result_json ?? n.result ?? n.resultPreview), args_json:decode(n.args_json ?? n.args ?? n.argsPreview),
    isError:n.isError ?? (['completed', 'failed', 'error', 'cancelled'].includes(n.status) ? n.status !== 'completed' : null),
    initial:n, completion:n, wait_ids:[], pending:false}));
  const identities = new Map(), jobs = new Map(), poisoned = new Set(), poisonedSessions = new Set();
  const jobKey = (n, job) => stable([n.session, job]);
  const idKey = n => stable([n.session, n.tool_use_id]);
  for (const row of rows) {
    for (const job of row.invalid_job_ids ?? []) poisoned.add(jobKey(row, job));
    if (row.invalid_jobs_truncated) poisonedSessions.add(row.session);
    const key = idKey(row);
    identities.set(key, [...identities.get(key) ?? [], row]);
    row.pending = row.data?.pending === true;
    if (row.pending) {
      row.completion = null;
      row.completion_index = null;
    }
    if (row.pending && row.name !== 'gz_wait' && typeof row.data?.job_id === 'string' && row.data.job_id) {
      const job = jobKey(row, row.data.job_id);
      jobs.set(job, [...jobs.get(job) ?? [], row]);
    }
  }
  const uniquePair = row => !!row.session && !!row.tool_use_id && identities.get(idKey(row)).length === 1
    && Number.isInteger(row.seq) && Number.isInteger(row.result_seq) && row.seq < row.result_seq
    && typeof row.isError === 'boolean';
  const paired = row => uniquePair(row) && row.args_json && typeof row.args_json === 'object' && !Array.isArray(row.args_json);
  for (const row of rows.filter(r => !paired(r))) {
    for (const job of [row.data?.job_id, row.name === 'gz_wait' ? row.args_json?.job_id : null]) {
      if (typeof job === 'string' && job) poisoned.add(jobKey(row, job));
    }
    if (row.tool_use_id && !uniquePair(row)) row.invalid = true;
  }
  for (const [key, originals] of jobs) {
    const job = originals[0].data.job_id, name = originals[0].name;
    let valid = !poisoned.has(key) && !poisonedSessions.has(originals[0].session)
      && new Set(originals.map(r => stable([r.name, r.args_json]))).size === 1
      && originals.every(r => paired(r) && r.data.ok === true && r.isError === false && r.data.tool === r.name);
    const waits = rows.filter(r => r.name === 'gz_wait' && r.session === originals[0].session
      && [r.args_json?.job_id, r.data?.job_id].includes(job));
    for (const wait of waits) {
      wait.interrupted = paired(wait) && originals.some(r => r.result_seq < wait.seq) && wait.result_code === 'CANCELLED'
        && wait.isError === true && wait.args_json.job_id === job
        && (wait.data?.job_id == null || wait.data.job_id === job) && (wait.data?.tool == null || wait.data.tool === name);
      valid &&= wait.interrupted || paired(wait) && originals.some(r => r.result_seq < wait.seq)
        && wait.args_json.job_id === job && wait.data?.job_id === job && wait.data.tool === name
        && (!wait.pending || wait.data.ok === true && wait.isError === false);
    }
    const completed = waits.filter(w => !w.pending && !w.interrupted);
    const body = w => Object.fromEntries(Object.entries(w.data ?? {}).filter(([k]) => !['job_id', 'tool'].includes(k)));
    if (!valid || new Set(completed.map(w => stable([w.isError, body(w)]))).size > 1) continue;
    for (const row of originals) {
      const eligible = waits.filter(w => row.result_seq < w.seq);
      row.wait_ids = eligible.map(w => w.tool_use_id);
      const final = eligible.filter(w => !w.pending && !w.interrupted).sort((a, b) => a.result_seq - b.result_seq)[0];
      if (!final) {
        const latest = eligible.filter(w => w.pending && !w.interrupted).sort((a, b) => b.result_seq - a.result_seq)[0];
        if (latest) {
          row.data = latest.data;
          row.result_json = row.data;
          row.result = JSON.stringify(row.data);
        }
        continue;
      }
      row.data = body(final);
      row.pending = false;
      row.completion = final.initial;
      row.completion_index = final.call_index;
      row.status = final.status;
      row.result_json = row.data;
      row.result = JSON.stringify(row.data);
      row.ended_at = final.ended_at;
      row.result_seq = final.result_seq;
    }
  }
  return rows.filter(r => r.name !== 'gz_wait').map(r => r.invalid
    ? {...r, data:null, status:'running', completion:null, completion_index:null} : r);
}
