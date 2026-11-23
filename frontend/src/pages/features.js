import {api} from '../api.js';
import {SERVICES, SLOTS} from '../domain.js';
import {state, orderFor, technicianFor} from '../store.js';
import {empty, esc, featureTable, formHandler, notify, panelTitle, signed, status} from '../ui.js';

function candidateOption(tech, order, plan) {
  const expired = tech.valid_through < order.service_date || tech.valid_through < state.session.business_date;
  const blocked = !tech.active || expired;
  return `<option value="${tech.id}" ${blocked ? 'disabled' : ''} ${!blocked && tech.id === plan?.technician_id ? 'selected' : ''}>
   ${esc(tech.name)} · ${tech.experience_years} 年 · ${!tech.active ? '停用' : expired ? '资质无法覆盖预约日' : '可试算'}</option>`;
}

function renderPlan(plan, order) {
  if (!plan) return empty('等待建立分析', '选择符合预约日期的技师，使用同品类的历史完单训练模型。');
  if (plan.status === 'queued') return `<div class="pending"><span class="pulse"></span><b>正在分析</b><p>后台正在处理。页面将自动刷新结果。</p></div>`;
  if (!plan.analysis) return `<div class="callout warn">${esc(plan.error_message || '当前没有分析结果')}</div>`;
  const model = plan.analysis;
  const tech = technicianFor(plan);
  return `<div class="analysis-top"><div class="model-meta"><span>历史完单</span><b>${model.history_count}<small> 条</small></b></div>
    <div class="model-meta"><span>留出集 MAE</span><b>${model.holdout_mae}<small> 分钟</small></b></div>
    <div class="model-meta"><span>训练 / 验证</span><b>${model.train_count}<small> / </small>${model.test_count}</b></div></div>
    ${featureTable(model)}
    <div class="analysis-foot"><span>训练样本均值 <b>${model.training_mean_minutes.toFixed(1)} 分钟</b></span>
    <span>验证起日 <b>${esc(model.holdout_since)}</b></span><span>Lasso α <b>${model.alpha}</b></span></div>
    <details class="trace"><summary>查看拟合快照</summary><p>技师 ${esc(tech?.name)} · 证书 ${esc(model.certificate)}</p>
      <code>${esc(model.history_checksum)}</code></details>
    ${plan.predicted_minutes === null ? '' : `<div class="trial-banner"><div><span>本单预测</span><strong>${plan.predicted_minutes} 分钟</strong></div>
      <div><span>相对受理预估</span><strong>${signed(plan.predicted_minutes - order.baseline_minutes)} 分钟</strong></div>
      <div>${status(plan.status)}<button class="line" id="open-review">进入派单复盘 →</button></div></div>`}`;
}

export function featuresPage(root, refresh, draw) {
  const {orders, plans, technicians, session} = state;
  const waiting = orders.filter(order => order.status === 'received');
  const selected = waiting.find(order => order.id === state.selectedOrder) || waiting[0];
  if (!selected) { root.innerHTML = empty('当前没有待派单工单', '先由客服受理订单，再生成新的分析。'); return; }
  const plan = plans.find(plan => orderFor(plan)?.id === selected.id);
  const matches = technicians.filter(tech => tech.skill === selected.service);
  const hasEligible = matches.some(tech => tech.active && tech.valid_through >= selected.service_date && tech.valid_through >= session.business_date);
  const canRun = session.role === 'dispatcher';
  root.innerHTML = `<div class="analysis-layout"><aside class="panel">${panelTitle('待派单订单', `${waiting.length} 张`)}
    <div class="queue">${waiting.map(order => `<button class="queue-row ${order.id === selected.id ? 'selected' : ''}"
      data-pick-order="${order.id}"><b>${esc(order.code)}</b><span>${esc(order.customer)} · ${SERVICES[order.service]}</span>
      <small>${esc(order.service_date)} · ${SLOTS[order.slot]}</small></button>`).join('')}</div></aside>
    <div class="analysis-body"><section class="panel case-sheet"><div><h2>${esc(selected.code)} <small>${esc(selected.neighborhood)}</small></h2>
      <p>${selected.area_m2} ㎡　·　污损 ${selected.dirt_level} 级　·　障碍物 ${selected.obstacles} 处　·　预估 ${selected.baseline_minutes} 分钟</p></div>
      ${canRun ? `<form id="analyze" class="inline-form"><label>候选技师<select name="technician_id" required>${matches.map(tech => candidateOption(tech, selected, plan)).join('')}</select></label>
       <button class="primary" type="submit" ${!hasEligible || plan?.status === 'queued' ? 'disabled' : ''}>${plan ? '重新分析' : '提交特征分析'}</button></form>` : ''}
      ${!hasEligible ? '<p class="form-error">暂无资质覆盖预约日的同技能技师。</p>' : ''}
      ${!session.worker_ready ? '<p class="form-error">分析进程暂不可用。排队方案会保留，进程恢复后继续。</p>' : ''}</section>
      <section class="panel analysis-panel">${panelTitle('特征筛选与线性回归', plan ? `方案 #${plan.id}` : '')}
      ${renderPlan(plan, selected)}
      <div class="panel-action field-links"><a href="#readiness" class="line" data-field-order="${selected.id}">查看派前核验 →</a>
        ${plan?.analysis ? `<a href="#scenarios" class="line" data-field-order="${selected.id}">对照工时假设 →</a>` : ''}</div>
      ${canRun && plan?.status === 'analyzed' ? '<div class="panel-action"><button id="trial" class="primary">生成派单试算</button></div>' : ''}</section>
    </div></div>`;
  root.querySelectorAll('[data-field-order]').forEach(link => {
    link.onclick = () => { state.selectedOrder = Number(link.dataset.fieldOrder); };
  });
  root.querySelectorAll('[data-pick-order]').forEach(button => button.onclick = () => {
    state.selectedOrder = Number(button.dataset.pickOrder);
    draw();
  });
  formHandler(root.querySelector('#analyze'), async data => {
    await api(`/orders/${selected.id}/analysis`, 'POST', {technician_id: Number(data.technician_id)});
    await refresh();
    notify('特征分析已排队');
  });
  const trial = root.querySelector('#trial');
  if (trial) trial.onclick = async () => {
    trial.disabled = true;
    try {
      const result = await api(`/plans/${plan.id}/trial`, 'POST');
      await refresh();
      notify(result.status === 'review_pre' ? '试算已生成，偏差超限，请主管复核' : '试算已生成，可前往复盘确认');
    } catch (error) { notify(error.message, true); }
    finally { trial.disabled = false; }
  };
  const go = root.querySelector('#open-review');
  if (go) go.onclick = () => { state.selectedPlan = plan.id; location.hash = '#review'; };
}
