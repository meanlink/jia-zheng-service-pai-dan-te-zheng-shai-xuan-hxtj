import {api} from '../api.js';
import {FEATURES, SERVICES, SLOTS} from '../domain.js';
import {state, orderFor, technicianFor} from '../store.js';
import {empty, esc, featureTable, formHandler, notify, panelTitle, signed, status} from '../ui.js';

const ELIGIBILITY = {
  pass: ['可启用', 'kept'], regression: ['误差变大', 'field-warn'], insufficient: ['高污损样本不足', 'field-warn'],
};

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
  const rule = model.rule;
  const fallback = model.rule_fallback;
  return `<div class="analysis-top"><div class="model-meta"><span>历史完单</span><b>${model.history_count}<small> 条</small></b></div>
    <div class="model-meta"><span>留出集 MAE</span><b>${model.holdout_mae}<small> 分钟</small></b></div>
    <div class="model-meta"><span>训练 / 验证</span><b>${model.train_count}<small> / </small>${model.test_count}</b></div></div>
    ${rule ? `<div class="analysis-foot"><span>排队时规则 <b>v${rule.version}</b></span>
      <span>特征组 <b>${rule.features.length} 项</b></span>
      ${fallback ? `<span class="flag">v${fallback.from_version} 不可解，已沿用旧规则</span>` : ''}</div>
      ${fallback ? `<div class="callout warn">新规则因 ${esc(fallback.reason)} 无法求解，已按 v${rule.version} 特征组完成分析。</div>` : ''}` : ''}
    ${featureTable(model)}
    <div class="analysis-foot"><span>训练样本均值 <b>${model.training_mean_minutes.toFixed(1)} 分钟</b></span>
    <span>验证起日 <b>${esc(model.holdout_since)}</b></span><span>Lasso α <b>${model.alpha}</b></span></div>
    <details class="trace"><summary>查看拟合快照</summary><p>技师 ${esc(tech?.name)} · 证书 ${esc(model.certificate)}</p>
      <code>${esc(model.history_checksum)}</code></details>
    ${plan.predicted_minutes === null ? '' : `<div class="trial-banner"><div><span>本单预测</span><strong>${plan.predicted_minutes} 分钟</strong></div>
      <div><span>相对受理预估</span><strong>${signed(plan.predicted_minutes - order.baseline_minutes)} 分钟</strong></div>
      <div>${status(plan.status)}<button class="line" id="open-review">进入派单复盘 →</button></div></div>`}`;
}

function errorRow(label, baseline, candidate, unit = '分钟') {
  const delta = candidate - baseline;
  const worse = delta > 0;
  return `<tr><td>${label}</td><td>${baseline} ${unit}</td><td>${candidate} ${unit}</td>
    <td class="${worse ? 'flag' : ''}">${signed(delta, 2)} ${unit}</td></tr>`;
}

function compareCard(row, category, session) {
  const base = row.baseline;
  const cand = row.candidate;
  const rule = category.active_rule;
  const [label, tone] = ELIGIBILITY[row.eligibility];
  const stale = rule && row.baseline_rule_id !== rule.id;
  const badge = row.enabled ? ['已启用', 'kept'] : stale ? ['现行规则已更换，需重新对照', 'field-warn'] : [label, tone];
  const canEnable = !row.enabled && session.role === 'supervisor' && row.eligibility === 'pass' &&
    !stale && rule;
  return `<article class="panel field-result"><div class="panel-title"><h2>特征组对照 #${row.id}</h2>
    <span class="tag ${badge[1]}">${esc(badge[0])}</span></div>
    <div class="field-body"><div class="field-metrics">
      <div><small>同批完单</small><strong>${cand.history_count} <small>条</small></strong></div>
      <div><small>同一验证起日</small><strong>${esc(cand.holdout_since)}</strong></div>
      <div><small>对照 / 候选特征</small><strong>v${esc(base.rule_version)} → ${cand.features.length} 项</strong></div></div>
      <p>现行 <b>${base.features.map(key => FEATURES[key][0]).join('、')}</b><br>
       候选 <b>${cand.features.map(key => FEATURES[key][0]).join('、')}</b></p>
      <p class="muted">${esc(row.note)} · ${esc(row.created_by)}</p>
      <div class="table-scroll"><table><thead><tr><th>留出集误差</th><th>现行规则</th><th>候选规则</th><th>变化</th></tr></thead><tbody>
        ${errorRow('总体 MAE', base.holdout_mae, cand.holdout_mae)}
        ${base.high_dirt_mae === null || cand.high_dirt_mae === null
          ? '<tr><td>高污损单 MAE</td><td colspan="3">验证集缺少高污损单，暂缓启用</td></tr>'
          : errorRow(`高污损单 MAE（污损 ≥ 4，${cand.high_dirt_count} 单）`, base.high_dirt_mae, cand.high_dirt_mae)}
      </tbody></table></div>
      <p class="muted">同批 ${esc(cand.history_checksum.slice(0, 12))} · 训练/验证 ${base.train_count}/${base.test_count} · 现行入选 ${base.selected.map(key => FEATURES[key][0]).join('、') || '无'} · 候选入选 ${cand.selected.map(key => FEATURES[key][0]).join('、') || '无'}</p>
      ${row.eligibility === 'insufficient' ? `<p class="field-callout">验证集高污损单 ${cand.high_dirt_count} 单，低于启用所需的 ${category.min_high_dirt_samples} 单，该组暂缓启用。</p>` : ''}
      ${row.eligibility === 'regression' ? '<p class="field-callout">候选规则在总体或高污损单上的误差变大，主管不能启用。</p>' : ''}
      ${stale ? '<p class="field-callout">现行规则已更换，请按新的现行规则重新对照后再启用。</p>' : ''}
      ${canEnable ? `<form id="enable-${row.id}" class="fields field-form"><label class="wide">启用说明
        <textarea name="note" minlength="6" maxlength="500" rows="2" required placeholder="记录总体与高污损单误差均未变大"></textarea></label>
        <p class="form-error wide" role="alert"></p>
        <button type="submit" class="primary wide">主管启用该品类特征组</button></form>` : ''}
    </div></article>`;
}

function rulePanel(category, session) {
  if (!category) return empty('该品类暂无历史完单', '完成同类工单回访后才可对照特征规则。');
  if (!category.can_compare) return `<div class="field-body"><p class="field-callout">该品类尚未设定现行特征规则。</p></div>`;
  const rule = category.active_rule;
  const sufficiency = category.holdout_high_dirt_count < category.min_high_dirt_samples
    ? `<p class="field-callout">验证集高污损单 ${category.holdout_high_dirt_count} 单，低于 ${category.min_high_dirt_samples} 单；此期间提交的特征组只能对照、不能启用。</p>` : '';
  const form = session.role === 'dispatcher' ? `<form id="compare-rule" class="fields field-form">
      <fieldset class="wide feature-picks"><legend>候选特征组（至少一项）</legend>
        ${category.features.map(key => `<label class="pick"><input type="checkbox" name="features" value="${key}"
          ${rule.features.includes(key) ? 'checked' : ''}> ${FEATURES[key][0]}</label>`).join('')}</fieldset>
      <label class="wide">对照说明<textarea name="note" minlength="6" maxlength="500" rows="2" required
        placeholder="说明换这组特征的原因，例如期望改善高污损单"></textarea></label>
      <p class="form-error wide" role="alert"></p>
      <button type="submit" class="primary wide">用同批完单与同一时间切分对照</button>
      <p class="muted wide">可增删任一特征；与现行规则完全相同时不能提交。</p></form>` : '';
  return `<div class="field-body"><div class="field-metrics">
      <div><small>现行规则</small><strong>v${rule.version}</strong></div>
      <div><small>现行特征组</small><strong>${rule.features.length} 项</strong></div>
      <div><small>同批完单 / 验证</small><strong>${category.history_count} / ${category.holdout_count}</strong></div></div>
    <p>现行特征：<b>${rule.features.map(key => FEATURES[key][0]).join('、')}</b></p>
    <p class="muted">对照与启用都使用同一批已结案完单，并以同一验证起日 ${esc(category.holdout_since)} 切分。</p>
    ${sufficiency}${form}</div>`;
}

export function featuresPage(root, refresh, draw) {
  const {orders, plans, technicians, session} = state;
  const waiting = orders.filter(order => order.status === 'received');
  const selected = waiting.find(order => order.id === state.selectedOrder) || waiting[0];
  const category = state.featureRules?.[selected?.service];
  const ruleBody = category ? rulePanel(category, session)
    : empty('尚未读取该品类规则', '等待品类特征规则加载后即可对照。');
  const comparisonBody = !category || !category.comparisons.length
    ? `<div class="panel field-body"><p class="muted">该品类暂无保存的特征组对照。</p></div>`
    : category.comparisons.map(row => compareCard(row, category, session)).join('');
  if (!selected) {
    root.innerHTML = `<div class="analysis-layout"><aside class="panel">${panelTitle('待派单订单', `${waiting.length} 张`)}
      <div class="queue"><p class="empty">当前没有待派单工单</p></div></aside>
      <div class="analysis-body"><section class="panel">${panelTitle('品类特征规则', '按品类选择')}${ruleBody}</section>
      <div class="field-stack">${comparisonBody}</div></div></div>`;
    return;
  }
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
      <section class="panel">${panelTitle(`品类特征规则 · ${SERVICES[selected.service]}`, '按品类选择一组特征')}${ruleBody}</section>
      <div class="field-stack">${comparisonBody}</div>
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
  bindRuleActions(root, refresh, selected.service);
}

function bindRuleActions(root, refresh, service) {
  const compare = root.querySelector('#compare-rule');
  formHandler(compare, async values => {
    const features = [...compare.querySelectorAll('input[name=features]:checked')].map(input => input.value);
    const result = await api(`/feature-rules/${service}/comparisons`, 'POST', {features, note: values.note});
    await refresh();
    notify(result.eligibility === 'pass' ? '对照已保存，主管可复核启用'
      : result.eligibility === 'insufficient' ? '对照已保存，但高污损单样本不足，暂缓启用' : '对照已保存，候选误差变大，不能启用');
  });
  root.querySelectorAll('form[id^=enable-]').forEach(form => formHandler(form, async values => {
    const id = form.id.slice('enable-'.length);
    try {
      await api(`/feature-rules/comparisons/${id}/enable`, 'POST', {note: values.note});
    } catch (error) {
      notify(error.message, true);
      await refresh();
      return;
    }
    await refresh();
    notify('该品类新分析已按新特征组切换');
  }));
}
