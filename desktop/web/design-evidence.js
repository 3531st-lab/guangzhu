import {esc} from './data.js';

const number=value=>typeof value==='number' && Number.isFinite(value) ? value.toLocaleString('zh-CN',{maximumFractionDigits:3}) : '未记录';
const statuses={missing:'未记录',partial:'记录不完整',recorded:'已记录',stale:'需要重算',unknown:'无法判定',
  fail:'未通过',pass:'适用硬性规则通过',matched:'摘要一致',mismatch:'摘要不一致',invalid:'记录无效',snapshot:'已核验脱敏快照'};
const integrity={missing:'缺少文件',recorded:'当前文件',verified:'归档校验一致',unverified:'归档未核验',mismatch:'摘要不一致',invalid:'文件无效'};
const checked=result=>result?.evidence?.schema==='guangzhu.design-evidence/1' && result.evidence.version===result.version ? result.evidence : null;
const mark=status=>`<span class="ev-state ev-${esc(status ?? 'unknown')}">${esc(statuses[status] ?? '未记录')}</span>`;

export function evidenceMarkup(result) {
  const item=checked(result);
  if (!item?.available) return '<section class="design-evidence"><h3>版本证据</h3><p class="muted">此版本尚无可核对的完整证据卡。</p></section>';
  const {model={},assumptions={},analysis={},rules={},review={},export:output={},usage={},weather={}}=item;
  const timing=analysis.elapsed_seconds==null?'未记录':`${number(analysis.elapsed_seconds)} 秒`;
  const labels=[['综合计算',analysis.status,`本次已记录计算耗时：${timing}`],
    ['工程规则',rules.status,`硬性未通过 ${number(rules.hard_failed)} 项；适用检查 ${number(rules.applicable)} 项${rules.unknown_count?`；另有 ${number(rules.unknown_count)} 项未知`:''}`],
    ['独立审核文件',review.status,`${number(review.count)} 份同版本记录；独立会话依据见执行记录`],
    ['交付文件',output.status,output.status==='snapshot'?output.note:`${number(output.count)} 个清单文件；不代替导出审批`]];
  const requirements=assumptions.requirements?.text;
  return `<section class="design-evidence" aria-label="当前版本证据"><header><h3>版本证据 · v${esc(item.version)}</h3>
    <button class="btn sm" data-action="download-design-evidence">下载证据 JSON</button></header>
    <p class="ev-intro">${esc(assumptions.name ?? item.project_id)} · ${number(model.modules)} 块组件
    ${model.parent_version!=null?` · 来自 v${esc(model.parent_version)}`:''}</p>
    ${model.reason?`<p>${esc(model.reason)}</p>`:''}
    <div class="ev-stages">${labels.map(([label,status,detail])=>`<div><b>${label}</b>${mark(status)}<small>${esc(detail)}</small></div>`).join('')}</div>
    <details class="ev-inputs" open><summary>输入假设与计算依据</summary><dl>
      <dt>屋面承重</dt><dd>${number(assumptions.load_capacity_kn_m2)} kN/m² · ${assumptions.load_verified?'用户已确认结构核定来源':'示意输入，待结构核定'}</dd>
      <dt>天气</dt><dd>${esc(weather.source_description ?? weather.source ?? '未记录')} · ${esc(weather.year ?? '年份未记录')}
        ${weather.used?` · ${esc(weather.used==='cache'?'本地缓存':weather.used==='network'?'联网取得':weather.used)}`:''}</dd>
      <dt>输入一致性</dt><dd>${esc(analysis.input_binding==='matched'?'遮挡与综合计算记录的输入签名一致':analysis.input_binding==='mismatch'?'当前输入与计算记录不符':'历史记录缺少完整输入签名')}</dd>
      <dt>整套输出</dt><dd>${esc(analysis.completion_status==='matched'?'完成清单与全部计算文件一致':analysis.completion_status==='mismatch'?'完成清单不一致，需要重算':'历史记录未保存完成清单')}</dd>
      ${requirements?`<dt>项目要求</dt><dd>${esc(requirements)}</dd>`:''}
      ${assumptions.economics_note?`<dt>经济假设</dt><dd>${esc(assumptions.economics_note)}</dd>`:''}
    </dl>${(analysis.notes ?? []).map(note=>`<p class="muted">${esc(note)}</p>`).join('')}
    ${analysis.missing?.length?`<p class="muted">缺少：${esc(analysis.missing.join('、'))}</p>`:''}</details>
    <details><summary>已记录耗时与模型用量</summary><p>${esc(usage.note)}</p>
      ${(usage.sessions ?? []).map(session=>`<div class="ev-session"><b>${esc(session.session_id)}</b><dl>
        <dt>会话时长</dt><dd>${number(session.elapsed_seconds)} 秒</dd>
        <dt>模型请求</dt><dd>${number(session.model_requests)}</dd>
        <dt>输入／输出 token</dt><dd>${number(session.tokens?.input)} / ${number(session.tokens?.output)}</dd>
        <dt>已记录费用</dt><dd>${session.costs?.length?session.costs.map(row=>`${esc(row.currency)} ${number(row.micros/1e6)}`).join('；'):'未记录'}${session.billing_complete?'':'（费用记录不完整）'}</dd>
      </dl></div>`).join('') || '<p class="muted">没有关联原生会话用量，不能据此认定模型调用或费用为零。</p>'}
      <p class="muted">人工工时、失败与重试总数：未记录。</p>${usage.error?`<p class="muted">${esc(usage.error)}</p>`:''}</details>
    <details><summary>文件摘要 · ${(item.sources ?? []).filter(row=>row.sha256).length} 份可读文件</summary>
      <div class="ev-sources">${(item.sources ?? []).map(row=>`<div><span>${esc(row.path)}</span><small>${esc(integrity[row.integrity] ?? '未核对')}</small>
        <code title="${esc(row.sha256 ?? '')}">${esc(row.sha256 ?? '—')}</code></div>`).join('')}</div></details>
    <p class="muted ev-note">${esc(item.note)}</p></section>`;
}

export function evidenceDownload(result) {
  const item=checked(result);
  if (!item?.available) throw new Error('当前版本没有可下载的证据卡。');
  const identifier=String(item.project_id ?? 'project').replace(/[^A-Za-z0-9_-]/g,'_');
  return {filename:`${identifier}-v${item.version}-evidence.json`,mime:'application/json;charset=utf-8',
    text:JSON.stringify(item,null,2)+'\n'};
}
