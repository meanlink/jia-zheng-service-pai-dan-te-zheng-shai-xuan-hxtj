import {api} from '../api.js';
import {SLOTS} from '../domain.js';
import {state} from '../store.js';
import {esc, formHandler, notify, optionTags, panelTitle} from '../ui.js';

const outcomes = {confirmed: '确认原预约', reschedule: '客户要求改期', moved: '完成改期'};

async function load(root, path, render) {
  root.textContent = '正在读取记录…';
  try {
    const rows = await api(path);
    if (root.isConnected) render(rows);
  } catch (error) {
    if (root.isConnected) root.textContent = error.message;
  }
}

export function timeOffPage(root) {
  return load(root, '/time-off', rows => {
    const canEdit = state.session.role === 'supervisor';
    const technicians = state.technicians.filter(tech => tech.active);
    root.innerHTML = `<section class="panel">${panelTitle('近期停工时段', `${rows.length} 条`)}
      <div class="table-scroll"><table><thead><tr><th>技师</th><th>停工日期</th><th>时段</th><th>原因</th>${canEdit ? '<th>操作</th>' : ''}</tr></thead>
      <tbody>${rows.map(row => `<tr><td>${esc(row.name)}</td><td>${esc(row.off_date)}</td><td>${SLOTS[row.slot]}</td>
        <td>${esc(row.reason)}</td>${canEdit ? `<td><button class="line" data-remove="${Number(row.id)}">撤销停工</button></td>` : ''}</tr>`).join('')}
      ${rows.length ? '' : `<tr><td colspan="${canEdit ? 5 : 4}">暂无近期停工时段</td></tr>`}</tbody></table></div></section>
      ${canEdit && technicians.length ? `<section class="panel">${panelTitle('登记停工')}
        <form id="time-off" class="fields"><label>技师<select name="technician_id">${technicians.map(tech =>
          `<option value="${Number(tech.id)}">${esc(tech.name)}</option>`).join('')}</select></label>
        <label>停工日期<input type="date" name="off_date" min="${esc(state.session.business_date)}" value="${esc(state.session.business_date)}" required></label>
        <label>停工时段<select name="slot">${optionTags(SLOTS)}</select></label>
        <label>停工原因<input name="note" minlength="6" maxlength="500" required></label>
        <p class="form-error" role="alert"></p><button class="primary" type="submit">保存停工</button></form></section>` : ''}`;
    formHandler(root.querySelector('#time-off'), async data => {
      await api('/time-off', 'POST', {...data, technician_id: Number(data.technician_id)});
      notify('停工时段已保存');
      await timeOffPage(root);
    });
    root.querySelectorAll('[data-remove]').forEach(button => {
      button.onclick = async () => {
        button.disabled = true;
        try {
          await api(`/time-off/${button.dataset.remove}`, 'DELETE');
          notify('已撤销停工');
          await timeOffPage(root);
        } catch (error) {
          notify(error.message, true);
          button.disabled = false;
        }
      };
    });
  });
}

export function visitContactPage(root, refresh) {
  return load(root, '/visit-contacts', rows => {
    const orders = state.orders.filter(order => order.status === 'received');
    root.innerHTML = `<section class="panel">${panelTitle('客户联络记录', '最近 100 条')}
      <div class="table-scroll"><table><thead><tr><th>工单</th><th>联络结果</th><th>预约日期</th><th>时段</th><th>备注</th></tr></thead>
      <tbody>${rows.map(row => `<tr><td>${esc(row.code)}</td><td>${outcomes[row.outcome]}</td><td>${esc(row.service_date)}</td>
        <td>${SLOTS[row.slot]}</td><td>${esc(row.note)}</td></tr>`).join('')}
      ${rows.length ? '' : '<tr><td colspan="5">暂无联络记录</td></tr>'}</tbody></table></div></section>
      ${state.session.role === 'intake' && orders.length ? `<section class="panel">${panelTitle('登记上门前联络')}
       <form id="visit-contact" class="fields"><label>待派工单<select name="order_id">${orders.map(order =>
         `<option value="${Number(order.id)}">${esc(order.code)} · ${esc(order.service_date)} ${SLOTS[order.slot]}</option>`).join('')}</select></label>
       <label>联络结果<select name="outcome">${optionTags(outcomes)}</select></label>
       <label data-new-slot hidden>新预约日期<input disabled required type="date" name="service_date" min="${esc(state.session.business_date)}"></label>
       <label data-new-slot hidden>新预约时段<select disabled name="slot">${optionTags(SLOTS)}</select></label>
       <label>联络备注<input name="note" minlength="6" maxlength="500" required></label>
       <p class="form-error" role="alert"></p><button class="primary" type="submit">保存联络记录</button></form></section>` : ''}`;
    const form = root.querySelector('#visit-contact');
    if (!form) return;
    form.elements.outcome.onchange = () => {
      const show = form.elements.outcome.value === 'moved';
      form.querySelectorAll('[data-new-slot]').forEach(label => {
        label.hidden = !show;
        label.style.display = show ? '' : 'none';
        label.querySelector('input, select').disabled = !show;
      });
    };
    form.elements.outcome.onchange();
    formHandler(form, async ({order_id, ...data}) => {
      await api(`/orders/${Number(order_id)}/visit-contacts`, 'POST', data);
      notify('客户联络记录已保存');
      await refresh();
    });
  });
}
