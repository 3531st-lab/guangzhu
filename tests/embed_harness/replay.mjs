// Replay actual harness logs; output is evidence for comparing with exported ledgers.
import fs from 'node:fs';
import {pathToFileURL} from 'node:url';
import {computeSteps} from '../../desktop/web/steps.js';
import {SessionRuns,parseTaskBrief} from './session-runs.js';

export function replayRows(rows, selectedSession) {
  const sessions = new Map(), types = new Set(), probes = [], errors = [], sessionRuns = new SessionRuns(), optionsByProject = new Map();
  for (const row of rows) {
    const m = row.message;
    types.add(m.type);
    if (row.direction === 'local' && m.type === 'run.open-options') sessionRuns.prepareOpen(m.session_id,{project:{id:m.project_id},run:m.run});
    if (row.direction === 'local' && m.type === 'run.options') optionsByProject.set(m.project_id,m.run);
    if (row.direction === 'out' && m.type === 'gz.start') {
      const run = parseTaskBrief(m.brief)?.run ?? optionsByProject.get(m.project_id) ?? {};
      sessionRuns.start(m.id,run);
    }
    if (row.direction === 'probe' || m.type === 'gz.unknown-test') probes.push({id:m.id,type:m.type,at:row.at});
    if (m.type === 'gz.error') {errors.push(m); sessionRuns.reject(m.re);}
    if (!m.session_id || row.direction !== 'in') continue;
    const s = sessions.get(m.session_id) ?? {session_id:m.session_id,approvals:[],nodes:[],op:'idle'};
    if (m.type === 'gz.session') {sessionRuns.accept(m); s.project_id = m.project_id;}
    if (m.type === 'gz.progress') sessionRuns.confirmOpen(m);
    s.run = sessionRuns.get(m.session_id);
    if (m.type === 'gz.approval') s.approvals.push({...m,received_at:Date.parse(row.at)});
    if (m.type === 'gz.progress') {s.nodes = m.nodes; s.op = m.op; s.at = row.at;}
    sessions.set(m.session_id,s);
  }
  return {message_types:[...types].sort(),errors,probes:probes.map(p => ({...p,replies:rows.filter(r => r.direction === 'in' && r.message.re === p.id).map(r => r.message)})),
    sessions:[...sessions.values()].filter(s => !selectedSession || s.session_id === selectedSession).map(s => ({...s,...computeSteps(s.nodes,{run:s.run,op:s.op,approvals:s.approvals,now:Date.parse(s.at)})}))};
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const file = process.argv[2];
  if (!file) throw new Error('Usage: node tests/embed_harness/replay.mjs LOG.messages.jsonl [SESSION_ID]');
  const input = fs.readFileSync(file,'utf8').trim();
  const rows = file.endsWith('.jsonl') ? input.split(/\r?\n/).filter(Boolean).map(JSON.parse) : JSON.parse(input).logs;
  console.log(JSON.stringify(replayRows(rows,process.argv[3]),null,2));
}
