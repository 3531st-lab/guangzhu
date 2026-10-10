import React, {useEffect, useState, useSyncExternalStore} from 'react';
import {Alert, Card, Space, Statistic, Table, Tag} from 'antd';
import {DATA} from '../extensions/main/client/data.js';
import {cardData, parseUser, roofGeometry, TOOL_NAMES} from './logic.js';
import {createBridge} from './bridge.js';

const statusLabels = {planned:'等待执行',awaiting_approval:'等你在下方审批',running:'正在计算',completed:'完成',failed:'失败',cancelled:'已取消'};
function RoofThumb({template}) {
  const geometry = roofGeometry(template);
  if (!geometry) return null;
  const zone = (row,kind) => row.circle ? <circle key={row.id} {...row.circle} className={kind}><title>{row.label}</title></circle>
    : <path key={row.id} d={row.path} className={kind}><title>{row.label}</title></path>;
  return <div className="gz-roof-thumb"><span>北 ↑</span><svg viewBox={geometry.viewBox} role="img" aria-label={`${template}屋顶轮廓、障碍物与禁区，北向上`}>
    <path d={geometry.outline} className="gz-outline"/>
    {geometry.keepouts.map(row => zone(row,'gz-keepout'))}{geometry.obstacles.map(row => zone(row,'gz-obstacle'))}
  </svg></div>;
}
function UserMessage({owner}) {
  const user = parseUser(owner?.node);
  const attachments = user.nonText.map(({label,count}) => <Tag key={label}>{label} ×{count}</Tag>);
  if (user.kind === 'plain') return <div className="gz-user-plain">{user.texts.map((text,i) => <span key={i}>{text}</span>)}{attachments}</div>;
  return <Card className="gz-user-brief" title={<span>{user.title}<small> · {user.projectId} · {user.roofName}</small></span>}>
    <Space wrap>{user.tags.map(tag => <Tag key={tag}>{tag}</Tag>)}</Space><details><summary>展开原文</summary><pre>{user.text}</pre></details>{attachments}
  </Card>;
}
function ToolCard({owner,bridge}) {
  const pending = useSyncExternalStore(bridge.subscribe,bridge.getPending);
  const nodes = useSyncExternalStore(bridge.subscribe,bridge.getNodes);
  const block = owner?.block;
  const card = cardData(pending === block?.name ? {...block,status:'awaiting_approval'} : block, nodes);
  const tone = card.status === 'failed' || card.status === 'cancelled' ? 'error' : card.status === 'completed' ? 'success' : 'processing';
  return <Card className="gz-tool" title={<Space wrap><b>{card.title}</b>
    <Tag color={tone}>{card.pending ? '计算中' : statusLabels[card.status] ?? card.status}</Tag></Space>}>
    {card.family === 'project' && card.templateId && <RoofThumb template={card.templateId}/>}
    {card.fallback ? <pre>{card.raw}</pre> : <>
      <div className="gz-metrics">{card.metrics.map((row,i) => <Statistic key={i} title={row.label} value={row.value}
        formatter={() => <span style={{color:row.tone ? `var(--agnes-status-${row.tone}-text)` : undefined}}>
          {String(row.value)}
        </span>}/>)}</div>
      {card.table && <Table size="small" pagination={false} scroll={{x:'max-content'}} rowKey="key"
        columns={card.table.columns.map((title,i) => ({title,dataIndex:String(i),key:String(i)}))}
        dataSource={card.table.rows.map((row,i) => Object.assign({key:i},...row.map((value,k) => ({[String(k)]:value}))))}/>}
      {card.warnings.map((warning,i) => <Alert key={i} type="warning" showIcon title={warning}/>)}
      {!card.metrics.length && !card.table && <div>{card.raw}</div>}
    </>}
  </Card>;
}
function ApprovalHint({ctx,bridge}) {
  const [tool,setTool] = useState('');
  useEffect(() => {
    let active = true, announced = '';
    const session = ctx.session.getSnapshot();
    const read = async () => {
      try {
        const result = await ctx.session.projection.read();
        if (!active) return;
        const running = n => n.kind === 'tool' && ['planned','running','awaiting_approval'].includes(n.status);
        const next = (result.value?.nodes ?? []).filter(running).at(-1)?.name ?? '';
        if (next && next !== announced) {
          if (announced) bridge.approval(announced,false,session);
          announced = next;
          setTool(next);
          bridge.approval(next,true,session);
        }
      } catch { /* The next projection update retries while the native card is mounted. */ }
    };
    read();
    const off = ctx.session.projection.subscribe(read);
    return () => {
      active = false;
      off();
      if (announced) bridge.approval(announced,false,session);
    };
  },[ctx,bridge]);
  if (!TOOL_NAMES.some(name => tool === name || tool.endsWith('_'+name))) return null;
  const exporting = tool === 'gz_export' || tool.endsWith('_gz_export');
  return <Alert className="gz-approval-hint" type="warning" showIcon title={exporting ? '导出需要你亲自批准：只点「仅允许这次」。' : '只会新增可回放的方案版本。'}
    description={exporting ? '选「本会话允许」，核对器会判结果验证不通过。' : '点「本会话允许」，这次运行不再为它弹窗。'}/>;
}
export function apply(ctx) {
  const bridge = createBridge(ctx);
  ctx.effect(() => () => bridge.dispose());
  const register = (name,id,component,key) => {
    let remove = () => {}, epoch = -1;
    const bind = () => {
      const next = ctx.slots.declarationEpoch(name);
      if (!ctx.slots.spec(name) || next === epoch) return;
      remove();
      epoch = next;
      remove = ctx.slots.register({name,id,priority:0,...(key ? {key} : {})},component);
    };
    const off = ctx.slots.subscribeDeclaration(name,bind);
    bind();
    ctx.effect(() => () => {
      off();
      remove();
    });
  };
  register('conversation.chat.node','gz-user',UserMessage,'user');
  for (const tool of TOOL_NAMES) register('tool.call.toolview','gz-'+tool,props => <ToolCard {...props} bridge={bridge}/>,DATA.toolPrefix+tool);
  register('conversation.approval.detail','gz-approval',() => <ApprovalHint ctx={ctx} bridge={bridge}/>);
  register('sidebar.brand.mark','gz-brand-mark',() => <span className="gz-mark" aria-label="光筑">●</span>);
  register('sidebar.brand.name','gz-brand-name',() => <span className="gz-brand"><b>光筑</b> · 基于 Agnes Harness</span>);
}
