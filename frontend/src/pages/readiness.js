import {api} from '../api.js';
import {ENTRY, fieldForm, mountFieldWorkspace, scopeFields, scopePayload, scopeSummary} from '../field-workspace.js';
import {esc} from '../ui.js';

const scopeStatuses = {pending: '待主管复核', approved: '已批准', rejected: '已驳回'};
const accessStatuses = {ready: '可入户', blocked: '入户受阻'};

function scopePanel({order, scope}, role) {
  const pending = scope?.status === 'pending';
  const label = scope ? scopeStatuses[scope.status] : '无补测记录';
  let form = '';
  if (order.status === 'received' && role === 'intake' && !pending) {
    form = fieldForm('scope-propose', scopeFields(order), '补测依据', '提交范围补测');
  }
  if (order.status === 'received' && role === 'supervisor' && pending) {
    form = fieldForm('scope-decide', `<label>处理结果<select name="decision">
      <option value="approved">批准并采用补测范围</option><option value="rejected">驳回并沿用原范围</option>
      </select></label>`, '复核说明', '提交主管复核');
  }
  return `<section class="panel"><div class="panel-title"><h2>作业范围补测</h2><span class="tag ${pending ? 'field-warn' : ''}">${label}</span></div>
    <div class="field-body"><p><strong>当前范围</strong> ${scopeSummary(order)}</p>
      ${scope ? `<dl class="field-details"><div><dt>补测版本</dt><dd>第 ${scope.revision_no} 版 · ${esc(scope.submitted_by)}</dd></div>
        <div><dt>受理时数据</dt><dd>${scopeSummary(scope.previous_scope)}</dd></div>
        <div><dt>补测范围</dt><dd>${scopeSummary(scope)}</dd></div><div><dt>补测依据</dt><dd>${esc(scope.reason)}</dd></div>
        ${scope.decision_note ? `<div><dt>复核说明</dt><dd>${esc(scope.decision_note)} · ${esc(scope.decided_by)}</dd></div>` : ''}</dl>` : ''}
      ${pending ? '<p class="field-callout">复核完成前暂停派单。采用补测范围后，原特征分析须重跑。</p>' : ''}</div>${form}</section>`;
}

function accessPanel({order, access}, role) {
  const form = order.status === 'received' && role === 'intake' ? fieldForm('access-edit',
    `<label>入户状态<select name="status"><option value="ready">可入户</option><option value="blocked" ${access?.status === 'blocked' ? 'selected' : ''}>入户受阻</option></select></label>
     <label>入户方式<select name="entry_method">${Object.entries(ENTRY).map(([key, label]) =>
       `<option value="${key}" ${key === access?.entry_method ? 'selected' : ''}>${label}</option>`).join('')}</select></label>`,
    '交接说明（请勿填写门禁密码）', '保存入户条件') : '';
  return `<section class="panel"><div class="panel-title"><h2>入户核验</h2>
    <span class="tag ${access?.status === 'blocked' ? 'field-warn' : 'kept'}">${access ? accessStatuses[access.status] : '未单独登记'}</span></div>
    <div class="field-body">${access ? `<dl class="field-details"><div><dt>入户方式</dt><dd>${ENTRY[access.entry_method]}</dd></div>
      <div><dt>交接说明</dt><dd>${esc(access.instructions)}</dd></div><div><dt>登记账号</dt><dd>${esc(access.updated_by)}</dd></div></dl>` :
      '<p class="muted">需要物业或现场联系人协调时，在此登记核验结果。</p>'}
      ${access?.status === 'blocked' ? '<p class="field-callout">入户条件落实后，客服可解除派单暂停。</p>' : ''}</div>${form}</section>`;
}

export function readinessPage(root, refresh) {
  mountFieldWorkspace(root, {
    refresh,
    preferred: order => order.code === 'QL-1105',
    render: (data, session) => `<div class="field-columns">${scopePanel(data, session.role)}${accessPanel(data, session.role)}</div>
      <div class="field-links"><a class="line" href="#features">打开特征工作台 →</a><a class="line" href="#scenarios">查看工时假设对照 →</a></div>`,
    bind: (_root, {order, scope}, action) => {
      const base = `/orders/${order.id}`;
      action('#scope-propose', values => api(`${base}/scope-revisions`, 'POST', scopePayload(values)), '已提交范围补测');
      action('#scope-decide', values => api(`${base}/scope-revisions/${scope.id}/decision`, 'POST', values), '已记录主管复核结果');
      action('#access-edit', values => api(`${base}/access`, 'PUT', values), '入户条件已保存');
    },
  });
}
