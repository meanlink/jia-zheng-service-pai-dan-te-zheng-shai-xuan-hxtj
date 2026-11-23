import {api} from '../api.js';
import {SERVICES, SLOTS} from '../domain.js';
import {ENTRY, fieldForm, mountFieldWorkspace, scopeSummary} from '../field-workspace.js';
import {esc, optionTags} from '../ui.js';

const arrivalLabels = {issued: '已发出 · 待回执', arrived: '已确认到场', access_failed: '入户失败'};

function briefCard(brief) {
  const s = brief.snapshot;
  return `<article class="panel field-result"><div class="panel-title"><h2>第 ${brief.edition} 版上门交接</h2>
    <span class="tag ${brief.status === 'access_failed' ? 'field-warn' : 'kept'}">${arrivalLabels[brief.status]}</span></div>
    <div class="field-body"><dl class="field-details"><div><dt>预约地点</dt><dd>${esc(s.neighborhood)} · ${SERVICES[s.service]}</dd></div>
      <div><dt>预约时段</dt><dd>${esc(s.service_date)} · ${SLOTS[s.slot]}</dd></div>
      <div><dt>派工技师</dt><dd>${esc(s.technician)} · 预计 ${s.estimated_minutes} 分钟</dd></div>
      <div><dt>作业范围</dt><dd>${scopeSummary(s.scope)}</dd></div>
      <div><dt>入户安排</dt><dd>${s.entry ? `${ENTRY[s.entry]} · ${esc(s.entry_instructions)}` : '见调度交接事项'}</dd></div>
      <div><dt>交接事项</dt><dd>${esc(brief.instructions)} · ${esc(brief.issued_by)}</dd></div>
      ${brief.arrival_note ? `<div><dt>到场回执</dt><dd>${esc(brief.arrival_note)} · ${esc(brief.arrival_by)}</dd></div>` : ''}</dl></div></article>`;
}

function actionPanel(data, session) {
  const current = data.briefs[0];
  const confirmed = data.plan_status === 'confirmed';
  const canIssue = confirmed && session.role === 'dispatcher' && (!current || current.status === 'access_failed');
  const canReport = confirmed && session.role === 'intake' && current?.status === 'issued';
  let form = '';
  if (canIssue) {
    const correction = current ? `<label>更新入户方式<select name="entry_method">${optionTags(ENTRY)}</select></label>
      <label class="wide">更新入户说明<textarea name="entry_instructions" minlength="6" maxlength="500" rows="2" required></textarea></label>` : '';
    form = fieldForm('brief-issue', correction, '调度交接事项', current ? '补发交接单' : '发出交接单');
  }
  if (canReport) form = fieldForm('brief-report', `<label>到场状态<select name="status"><option value="arrived">已到场</option>
    <option value="access_failed">入户失败</option></select></label>`, '现场回执说明', '登记到场回执');
  return `<section class="panel"><div class="panel-title"><h2>交接与到场回执</h2></div>
    <div class="field-body">${confirmed ? '<p>发出交接后，客服确认技师已到场才可登记完工回访。</p>' :
      '<p class="muted">调度确认派工后，可以发出上门交接单。</p>'}
      ${current?.status === 'access_failed' ? '<p class="field-callout">入户失败。请调度写明新的接应安排并补发，再登记到场回执。</p>' : ''}</div>${form}</section>`;
}

export function handoverPage(root, refresh) {
  mountFieldWorkspace(root, {
    refresh,
    preferred: order => order.status === 'assigned',
    render: (data, session) => `<div class="field-columns">${actionPanel(data, session)}<div class="field-stack" id="brief-history">
      ${data.briefs.map(briefCard).join('') || '<div class="panel field-body"><p class="muted">该工单尚未发出交接单。</p></div>'}</div></div>
      <div class="field-links"><a class="line" href="#review">打开派单复盘 →</a><a class="line" href="#readiness">查看入户和补测记录 →</a></div>`,
    bind: (_root, data, action) => {
      const url = `/plans/${data.plan_id}/handover`;
      action('#brief-issue', ({note, entry_method, entry_instructions}) => api(url, 'POST', {
        note, ...(entry_method ? {correction: {entry_method, entry_instructions}} : {}),
      }), '已发出交接单');
      action('#brief-report', values => api(`${url}/${data.briefs[0].id}/arrival`, 'POST', values), '已登记到场回执');
    },
  });
}
