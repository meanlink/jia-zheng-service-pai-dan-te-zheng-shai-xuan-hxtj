import {api} from '../api.js';
import {EVENTS, SERVICES, SLOTS} from '../domain.js';
import {state, orderFor, technicianFor} from '../store.js';
import {empty, esc, formHandler, notify, panelTitle, signed, status} from '../ui.js';

function formFor(plan, role) {
  if (role === 'supervisor' && ['review_pre','review_post'].includes(plan.status)) {
    return `<form id="resolve" data-endpoint="review" class="fields single">
      <label>复核意见<textarea name="note" minlength="6" maxlength="500" required placeholder="记录现场原因与处理决定"></textarea></label>
      <p class="form-error" role="alert"></p><button type="submit" class="primary">${plan.status === 'review_pre' ? '复核通过' : '复核结案'}</button></form>`;
  }
  if (role === 'intake' && plan.status === 'confirmed') {
    return `<form id="resolve" data-endpoint="followup" class="fields single">
      <label>实际作业工时（分钟）<input name="actual_minutes" type="number" min="15" max="720" required></label>
      <label>回访记录<textarea name="note" minlength="6" maxlength="500" required></textarea></label>
      <p class="form-error" role="alert"></p><button type="submit" class="primary">保存回访</button></form>`;
  }
  if (role === 'dispatcher' && ['trial','reviewed'].includes(plan.status)) {
    return `<form id="resolve" data-endpoint="confirm" class="panel-action"><p class="form-error" role="alert"></p>
      <button type="submit" class="primary">确认派单</button></form>`;
  }
  return '';
}

function reviewText(plan, order) {
  if (plan.status === 'review_pre') return `预测 ${plan.predicted_minutes} 分钟，比受理预估 ${signed(plan.predicted_minutes - order.baseline_minutes)} 分钟。请主管复核后再确认派单。`;
  if (plan.status === 'review_post') return `实绩与预测相差 ${signed(plan.actual_minutes - plan.predicted_minutes)} 分钟。请主管确认回访原因后结案。`;
  if (plan.status === 'confirmed') return '调度已确认工单。服务完成后请客服登记实绩和回访记录。';
  return '';
}

export function reviewPage(root, refresh, draw) {
  const visible = state.plans.filter(plan => plan.predicted_minutes !== null && orderFor(plan));
  const open = visible.filter(plan => plan.status !== 'closed');
  const recent = visible.filter(plan => plan.status === 'closed' && (plan.analysis || plan.followup_note !== '历史完单回执'));
  const candidates = [...open, ...recent].slice(0, 24);
  const plan = candidates.find(plan => plan.id === state.selectedPlan) || candidates[0];
  if (!plan) { root.innerHTML = empty('暂无试算或待复核方案', '在特征工作台生成试算后，即可确认派单并登记回访。'); return; }
  const order = orderFor(plan);
  const tech = technicianFor(plan);
  const callout = reviewText(plan, order);
  root.innerHTML = `<div class="review-layout"><section class="panel review-sheet">${panelTitle('工时差异与交接', order.code)}
    <div class="review-lead"><div><h3>${esc(order.customer)} · ${esc(order.neighborhood)}</h3>
      <p>${SERVICES[order.service]} · ${esc(order.service_date)} ${SLOTS[order.slot]} · ${esc(tech?.name)}</p></div>${status(plan.status)}</div>
    <div class="readings"><div><span>受理预估</span><b>${order.baseline_minutes}</b><small>分钟</small></div>
      <div><span>模型预测</span><b>${plan.predicted_minutes}</b><small>分钟</small></div>
      <div><span>实际工时</span><b>${plan.actual_minutes ?? '—'}</b><small>分钟</small></div></div>
    <p class="threshold">复核阈值 ±${plan.deviation_limit} 分钟</p>
    ${callout ? `<div class="callout ${plan.status.startsWith('review_') ? 'warn' : ''}">${esc(callout)}</div>` : ''}
    ${[['派单前复核',plan.pre_review_note],['客服回访',plan.followup_note],['复盘结论',plan.post_review_note]]
      .filter(([,note]) => note).map(([label,note]) => `<div class="memo"><b>${label}</b><p>${esc(note)}</p></div>`).join('')}
    ${['confirmed', 'review_post', 'closed'].includes(plan.status) ? `<div class="panel-action field-links">
      <a class="line" href="#handover" id="open-handover">查看上门交接 →</a></div>` : ''}
    ${formFor(plan, state.session.role)}
    <div class="timeline-wrap">${panelTitle('工单轨迹')}<ol class="timeline" id="timeline"><li>正在读取…</li></ol></div>
    </section><aside class="panel">${panelTitle('交接队列', `${open.length} 张待完成`)}<div class="queue">
      ${candidates.map(item => `<button data-pick-plan="${item.id}" class="queue-row ${item.id === plan.id ? 'selected' : ''}">
        <b>${esc(orderFor(item).code)}</b><span>${esc(orderFor(item).customer)}</span>${status(item.status)}</button>`).join('')}
    </div></aside></div>`;
  const handover = root.querySelector('#open-handover');
  if (handover) handover.onclick = () => { state.selectedOrder = order.id; };
  const timeline = root.querySelector('#timeline');
  api(`/orders/${order.id}/events`).then(events => {
    timeline.innerHTML = events.length ? events.map(event => `<li><b>${esc(EVENTS[event.event] || event.event)}</b>
      <small>${esc(event.actor)} · ${esc(event.happened_at.replace('T',' '))}</small></li>`).join('') : '<li>暂无工单轨迹</li>';
  }).catch(error => { timeline.textContent = error.message; });
  root.querySelectorAll('[data-pick-plan]').forEach(button => button.onclick = () => {
    state.selectedPlan = Number(button.dataset.pickPlan);
    draw();
  });
  const form = root.querySelector('#resolve');
  formHandler(form, async data => {
    if ('actual_minutes' in data) data.actual_minutes = Number(data.actual_minutes);
    await api(`/plans/${plan.id}/${form.dataset.endpoint}`, 'POST', Object.keys(data).length ? data : undefined);
    await refresh();
    notify('工单进度已更新');
  });
}
