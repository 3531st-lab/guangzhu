import {esc} from './data.js';

const SCHEMA = 'guangzhu.design-diagnostics/1';
const numeric = value => Number.isFinite(value) ? value.toLocaleString('zh-CN', {maximumFractionDigits:6}) : '未提供';
const valueText = value => value == null ? '未提供' : typeof value === 'number' ? numeric(value) :
  typeof value === 'object' ? JSON.stringify(value) : String(value);
const safeIds = values => Array.isArray(values) && values.every(value => typeof value === 'string') && new Set(values).size === values.length;

function current(result) {
  const diagnostics=result?.diagnostics;
  if (!diagnostics || diagnostics.schema!==SCHEMA || !Number.isInteger(result.version) ||
      diagnostics.version!==result.version || result.design?.version!==result.version) {
    throw new Error('问题定位与当前设计版本不一致，请重新打开本版本结果。');
  }
  if (!diagnostics.available) throw new Error(diagnostics.reason || '此版本尚无可用诊断。');
  return diagnostics;
}

function target(result, issue) {
  const modules=new Set((result.design?.modules ?? []).map(module=>module.id));
  if (!issue.located || !safeIds(issue.module_ids) || !issue.module_ids.length ||
      issue.module_ids.some(id=>!modules.has(id)) || !safeIds(issue.string_ids) ||
      !Array.isArray(issue.plane_ids) || !issue.plane_ids.every(id=>Number.isInteger(id) && id>0)) {
    throw new Error(issue.location_reason || '此问题缺少完整且有效的对象定位证据。');
  }
  const locked=new Set([...(result.locked_modules ?? []),...(result.design.locked_module_ids ?? []),...(issue.locked_module_ids ?? [])]);
  return {key:issue.key,version:result.version,module_ids:[...issue.module_ids],
    plane_ids:[...issue.plane_ids],string_ids:[...issue.string_ids],
    locked_module_ids:issue.module_ids.filter(id=>locked.has(id))};
}

/** Return an intent only. The caller owns highlighting, preview requests and confirmation. */
export function diagnosticAction(result, key, action) {
  const diagnostics=current(result), matches=(diagnostics.issues ?? []).filter(issue=>issue.key===key);
  if (matches.length!==1) throw new Error('该诊断已不存在，请重新查看当前版本。');
  const issue=matches[0], selected=target(result,issue);
  if (action==='locate') return {kind:'locate',...selected,
    mode:issue.rule_id==='S01' ? 'heat' : ['E08','E10'].includes(issue.rule_id) ? 'wiring' : issue.rule_id==='L01' ? 'wind' : 'light'};
  if (result.editable!==true) throw new Error('此记录只读；打开本机项目后才能预览修改。');
  const locked=new Set(selected.locked_module_ids), editable=selected.module_ids.filter(id=>!locked.has(id));
  if (!editable.length) throw new Error('相关组件全部已锁定；不会自动解锁或修改。');
  if (action==='edit') return {kind:'edit',...selected,module_ids:editable};
  if (action!=='fix') throw new Error('不支持的诊断操作。');
  const fix=issue.fix, operation=fix?.ops?.[0];
  if (issue.rule_id!=='S01' || !fix || !Array.isArray(fix.ops) || fix.ops.length!==1 || operation?.op!=='remove_modules' ||
      !safeIds(operation.module_ids) || operation.module_ids.length!==editable.length ||
      operation.module_ids.some(id=>!editable.includes(id)) || typeof fix.reason!=='string' || !fix.reason.trim()) {
    throw new Error('该问题没有与当前锁定状态一致的修复预览，请重新查看结果。');
  }
  return {kind:'preview',key,version:result.version,
    ops:[{op:'remove_modules',module_ids:[...operation.module_ids]}],reason:fix.reason,detailed:true,
    retained_locked_ids:[...selected.locked_module_ids]};
}

function detailMarkup(issue) {
  const details=(issue.details ?? []).slice(0,12);
  if (!details.length) return '';
  const line = row => issue.rule_id==='S01' ? `${row.id} · ${numeric(row.total_loss_pct)}%${row.main_cause ? ' · 主要来源 '+row.main_cause : ''}` :
    issue.rule_id==='E10' ? `${row.id} · 压降 ${numeric(row.drop_pct)}% · 路径${row.routing_status==='blocked' ? '不可达' : row.routing_status==='ok' ? '可达' : '未提供'}` :
    issue.rule_id==='L01' ? `P${row.id} · 附加荷载 ${numeric(row.added_kn_m2)} / ${numeric(row.capacity_kn_m2)} kN/㎡ · ${row.verified===true ? '核定输入' : '示意输入，待核定'}` : String(row.id);
  return `<details class="dd-evidence"><summary>对象证据 · ${issue.module_ids.length} 块组件</summary><ul>${details.map(row=>`<li>${esc(line(row))}</li>`).join('')}</ul>
    ${(issue.details?.length ?? 0)>details.length ? `<p class="muted">另有 ${issue.details.length-details.length} 条；定位包含全部已列明对象。</p>` : ''}</details>`;
}

function button(result, issue, action, label) {
  let disabled=false,reason='';
  try {diagnosticAction(result,issue.key,action);} catch(error) {disabled=true;reason=error.message;}
  return `<button class="btn sm" data-diagnostic-action="${action}" data-diagnostic-key="${esc(issue.key)}" ${disabled ? `disabled title="${esc(reason)}"` : ''}>${esc(label)}</button>`;
}

/** Pure markup: no requests, DOM mutation, event handlers or automatic repairs. */
export function diagnosticsMarkup(result, {selectedKey=null}={}) {
  let diagnostics;
  try {diagnostics=current(result);} catch(error) {
    return `<section class="design-diagnostics"><h3>问题定位</h3><p class="muted">${esc(error.message)}</p></section>`;
  }
  if (!diagnostics.issues?.length) return `<section class="design-diagnostics"><h3>问题定位 · v${result.version}</h3><p>${esc(diagnostics.reason || '没有未通过项。')}</p></section>`;
  return `<section class="design-diagnostics" aria-label="当前版本问题定位"><h3>问题定位 · v${result.version}</h3>
    <p class="muted">定位只改变视角；修改与修复均须先预览，再确认保存。</p>
    ${result.editable!==true ? '<p class="dd-note">归档记录只读，可查看本版本问题。</p>' : ''}
    ${diagnostics.issues.map(issue=>`<article class="dd-issue ${issue.key===selectedKey ? 'dd-selected' : ''}" data-diagnostic-issue="${esc(issue.key)}">
      <div class="dd-title"><b>${esc(issue.rule_id)}</b><strong>${esc(issue.title)}</strong><span class="dd-level ${issue.level==='hard' ? 'dd-hard' : ''}">${issue.level==='hard' ? '硬性未通过' : '建议项'}</span></div>
      <p>当前值 ${esc(valueText(issue.value))}${esc(issue.unit)} · 限值 ${esc(valueText(issue.limit))}${esc(issue.unit)}</p>
      ${issue.evidence ? `<p>${esc(issue.evidence)}</p>` : ''}${issue.hint ? `<p class="dd-note">${esc(issue.hint)}</p>` : ''}
      ${issue.located ? `<p>已关联 ${issue.module_ids.length} 块组件${issue.plane_ids.length ? ` · 坡面 ${esc(issue.plane_ids.map(id=>'P'+id).join('、'))}` : ''}${issue.string_ids.length ? ` · ${issue.string_ids.length} 条组串` : ''}；其中 ${issue.locked_module_ids.length} 块已锁定。</p>` : `<p class="dd-unlocated">${esc(issue.location_reason)}</p>`}
      ${issue.location_note ? `<p class="muted">${esc(issue.location_note)}</p>` : ''}${detailMarkup(issue)}
      ${issue.located ? `<div class="dd-actions">${button(result,issue,'locate','定位')}${button(result,issue,'edit','进入局部修改')}${issue.fix ? button(result,issue,'fix',issue.fix.label) : ''}</div>` : ''}
      ${issue.fix ? `<p class="dd-note">${esc(issue.fix.note)}</p>` : issue.fix_unavailable_reason ? `<p class="dd-note">${esc(issue.fix_unavailable_reason)}</p>` : ''}
      ${issue.source_ref ? `<details class="dd-source"><summary>检查依据</summary><p>${esc(issue.source_ref)}</p></details>` : ''}
    </article>`).join('')}</section>`;
}
