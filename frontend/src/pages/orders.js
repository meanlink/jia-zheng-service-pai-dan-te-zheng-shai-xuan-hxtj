import {api} from '../api.js';
import {ORDER_STATUS, SERVICES, SLOTS} from '../domain.js';
import {state} from '../store.js';
import {empty, esc, formHandler, notify, optionTags, panelTitle, status} from '../ui.js';

function receiveForm(session) {
  if (session.role !== 'intake') return `<aside class="panel field-note">${panelTitle('受理交接')}
    <p>核对作业面积、污损等级与客服预估工时。选择待派单工单进入特征工作台。</p></aside>`;
  return `<aside class="panel receive-panel">${panelTitle('受理新订单')}
    <form id="receive" class="fields">
      <label>工单号<input name="code" placeholder="QL-1105" pattern="[A-Z0-9][A-Z0-9\\-]{2,31}" required></label>
      <label>客户称呼<input name="customer" maxlength="60" minlength="2" placeholder="如 方女士" required></label>
      <label class="wide">服务片区<input name="neighborhood" maxlength="80" minlength="2" placeholder="区 · 街道" required></label>
      <label>服务品类<select name="service">${optionTags(SERVICES)}</select></label>
      <label>预约时段<select name="slot">${optionTags(SLOTS)}</select></label>
      <label>预约日<input name="service_date" type="date" value="${esc(session.business_date)}" min="${esc(session.business_date)}" required></label>
      <label>受理预估（分钟）<input name="baseline_minutes" type="number" min="15" max="720" value="120" required></label>
      <label>作业面积（㎡）<input name="area_m2" type="number" min="10" max="500" value="86" required></label>
      <label>污损等级<select name="dirt_level">${[1,2,3,4,5].map(n => `<option ${n === 3 ? 'selected' : ''}>${n}</option>`).join('')}</select></label>
      <label>障碍物（处）<input name="obstacles" type="number" min="0" max="15" value="2" required></label>
      <label>现场备料<select name="supplies"><option value="yes">已备</option><option value="no">未备</option></select></label>
      <p class="form-error wide" role="alert"></p><button type="submit" class="primary wide">登记工单</button>
    </form></aside>`;
}

export function ordersPage(root, refresh) {
  const {orders,session} = state;
  const active = orders.filter(order => order.status !== 'followed_up');
  const todays = active.filter(order => order.service_date === session.business_date);
  const pending = active.filter(order => order.status === 'received');
  root.innerHTML = `<div class="intake-strip"><div><span>今日预约</span><b>${todays.length}</b></div>
    <div><span>待派单</span><b>${pending.length}</b></div><div><span>已确认待回访</span><b>${active.length - pending.length}</b></div></div>
    <div class="split"><section class="panel">${panelTitle('待办工单', `${active.length} 张`)}
      ${active.length ? `<div class="table-scroll"><table><thead><tr><th>工单 / 服务片区</th><th>预约</th>
        <th>受理预估</th><th>进度</th><th><span class="sr-only">查看</span></th></tr></thead><tbody>
        ${active.map(order => `<tr><td><strong>${esc(order.code)}</strong><small>${esc(order.customer)} · ${esc(order.neighborhood)}</small></td>
        <td>${SERVICES[order.service]}<small>${esc(order.service_date.slice(5))} · ${SLOTS[order.slot]}</small></td>
        <td class="numeric">${order.baseline_minutes} <small class="inline">分钟</small></td>
        <td>${order.plan_status ? status(order.plan_status) : esc(ORDER_STATUS[order.status])}</td>
        <td><button class="line" data-order="${order.id}" data-plan="${order.plan_id ?? ''}" data-state="${order.status}">查看 →</button></td></tr>`).join('')}
        </tbody></table></div>` : empty('待办工单已清空', '客服可从右侧受理下一张订单。')}</section>${receiveForm(session)}</div>`;
  root.querySelectorAll('[data-order]').forEach(button => button.onclick = () => {
    state.selectedOrder = Number(button.dataset.order);
    if (button.dataset.state === 'assigned') {
      state.selectedPlan = Number(button.dataset.plan);
      location.hash = '#review';
    } else location.hash = '#features';
  });
  formHandler(root.querySelector('#receive'), async (data) => {
    for (const key of ['area_m2','dirt_level','obstacles','baseline_minutes']) data[key] = Number(data[key]);
    data.supplies = data.supplies === 'yes';
    const order = await api('/orders','POST',data);
    await refresh();
    notify(`${order.code} 已受理，可交给调度分析`);
  });
}
