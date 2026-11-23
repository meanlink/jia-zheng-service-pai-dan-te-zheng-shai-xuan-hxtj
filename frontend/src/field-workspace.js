import {api} from './api.js';
import {SERVICES, SLOTS} from './domain.js';
import {state} from './store.js';
import {esc, formHandler, notify} from './ui.js';

export const ENTRY = {customer: '客户当面接应', concierge: '物业访客放行', keyholder: '现场联系人接应'};

export function scopeFields(scope) {
  return `<label>作业面积（㎡）<input type="number" name="area_m2" min="10" max="500" value="${esc(scope.area_m2)}" required></label>
    <label>污损等级<input type="number" name="dirt_level" min="1" max="5" value="${esc(scope.dirt_level)}" required></label>
    <label>障碍数<input type="number" name="obstacles" min="0" max="15" value="${esc(scope.obstacles)}" required></label>
    <label>现场耗材<select name="supplies"><option value="yes" ${scope.supplies ? 'selected' : ''}>有</option>
      <option value="no" ${scope.supplies ? '' : 'selected'}>无</option></select></label>`;
}

export function scopePayload(values) {
  return {area_m2: Number(values.area_m2), dirt_level: Number(values.dirt_level),
    obstacles: Number(values.obstacles), supplies: values.supplies === 'yes', note: values.note};
}

export function scopeSummary(scope) {
  return `${esc(scope.area_m2)} ㎡ · 污损 ${esc(scope.dirt_level)} 级 · ${esc(scope.obstacles)} 处障碍 · 耗材${scope.supplies ? '有' : '无'}`;
}

export function fieldForm(id, fields, noteLabel, action) {
  return `<form id="${id}" class="fields field-form">${fields}
    <label class="wide">${noteLabel}<textarea name="note" minlength="6" maxlength="500" rows="2" required></textarea></label>
    <p class="form-error wide" role="alert"></p><button type="submit" class="primary wide">${action}</button></form>`;
}

export function mountFieldWorkspace(root, {preferred, render, bind, refresh}) {
  const orders = state.orders.filter(order => order.status !== 'followed_up' || !/^QL-H[CA]-\d{3}$/.test(order.code));
  const selected = orders.find(order => order.id === state.selectedOrder) || orders.find(preferred) || orders[0];
  if (!selected) { root.innerHTML = '<p class="muted">暂无可处理工单。</p>'; return; }
  root.innerHTML = `<div class="panel field-picker"><div class="field-select"><label for="field-order">工单</label><select id="field-order">${orders.map(order =>
    `<option value="${order.id}" ${order.id === selected.id ? 'selected' : ''}>${esc(order.code)} · ${esc(order.customer)}</option>`).join('')}
    </select></div><div class="field-order-summary"></div></div><div class="field-content" aria-live="polite"></div>`;
  const select = root.querySelector('#field-order');
  const content = root.querySelector('.field-content');
  let revision = 0;

  async function load() {
    const id = Number(select.value);
    const request = ++revision;
    state.selectedOrder = id;
    try {
      const data = await api(`/orders/${id}/fieldwork`);
      if (!root.isConnected || request !== revision) return;
      const {order} = data;
      state.selectedPlan = data.plan_id;
      root.querySelector('.field-order-summary').textContent =
        `${order.neighborhood} · ${SERVICES[order.service]} · ${order.service_date} ${SLOTS[order.slot]}`;
      content.innerHTML = render(data, state.session);
      bind(content, data, (selector, action, message) => {
        formHandler(content.querySelector(selector), async values => {
          await action(values);
          notify(message);
          if (root.isConnected && request === revision) await refresh();
        });
      });
    } catch (error) {
      if (!root.isConnected || request !== revision) return;
      content.innerHTML = `<div class="panel field-body"><p role="alert">${esc(error.message)}</p>
        <button type="button" class="line">重试</button></div>`;
      content.querySelector('button').onclick = load;
    }
  }

  function selectOrder() {
    root.querySelector('.field-order-summary').textContent = '';
    content.innerHTML = '<p class="muted">正在读取工单…</p>';
    load();
  }
  select.onchange = selectOrder;
  selectOrder();
}
