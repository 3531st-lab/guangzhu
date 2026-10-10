import fs from 'node:fs';

// Read committed evidence directly. No synthetic result fields are added.
export function ledgerFixture(relative) {
  const path = new URL('../../'+relative,import.meta.url);
  const events = fs.readFileSync(path,'utf8').trim().split(/\r?\n/).map(JSON.parse);
  const session = events.find(e => e.type === 'session/start')?.data.key;
  const calls = new Map(events.filter(e => e.type === 'tool/call').map(e => [e.data.toolUseId,e]));
  const results = new Map(events.filter(e => e.type === 'tool/result').map(e => [e.data.toolUseId,e]));
  const asks = new Map(events.filter(e => e.type === 'approval/asked').map(e => [e.data.requestId,e]));
  const content = e => (e?.data.content ?? []).filter(b => b.type === 'text').map(b => b.text).join('');
  const nodes = events.flatMap(e => {
    if (e.type === 'assistant/message') return [{kind:'text',text:Array.from(content(e)).slice(0,300).join('')}];
    if (e.type === 'tool/call' && /(?:^|_)(gz_\w+|subagent_fork)$/.test(e.data.name)) {
      const result = results.get(e.data.toolUseId);
      return [{kind:'tool',name:e.data.name,status:result?.data.isError ? 'failed' : result ? 'completed' : 'running',
        session,args_json:e.data.args,isError:result?.data.isError,
        started_at:e.ts,ended_at:result?.ts,result:content(result),seq:e.seq,result_seq:result?.seq,tool_use_id:e.data.toolUseId}];
    }
    if (e.type === 'approval/decided') {
      const ask = asks.get(e.data.requestId), call = calls.get(ask?.data.toolUseId);
      return call ? [{kind:'approval',tool:call.data.name,verdict:e.data.verdict,seq:e.seq,
        session,tool_use_id:call.data.toolUseId,via:e.data.via}] : [];
    }
    return [];
  });
  return {events,nodes,result:seq => JSON.parse(content(events.find(e => e.seq === seq)))};
}
