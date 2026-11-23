import {api} from '../api.js';
import {SERVICES} from '../domain.js';
import {state} from '../store.js';
import {empty, esc, formHandler, notify, panelTitle} from '../ui.js';

export function techniciansPage(root, refresh, draw) {
  const {technicians,session} = state;
  const term = session.business_date;
  const expiringCutoff = new Date(`${term}T00:00:00Z`);
  expiringCutoff.setUTCDate(expiringCutoff.getUTCDate() + 14);
  const soon = expiringCutoff.toISOString().slice(0,10);
  const pick = technicians.find(tech => tech.id === state.selectedTech) ||
    technicians.find(tech => tech.valid_through < term) || technicians[0];
  const expiry = (tech) => !tech.active ? ['停用', 'warn'] : tech.valid_through < term ? ['已过期','warn'] :
    tech.valid_through <= soon ? ['14 天内到期','warn'] : ['有效','good'];
  if (!pick) { root.innerHTML = empty('暂无技师', '请先载入技师资料。'); return; }
  const expired = technicians.filter(tech => tech.active && tech.valid_through < term).length;
  root.innerHTML = `<div class="split"><section class="panel">${panelTitle('在册证书', `${expired} 张证书已过期`)}
    <div class="table-scroll"><table><thead><tr><th>技师</th><th>技能 / 经验</th><th>证书截止</th><th>校验</th><th><span class="sr-only">查看</span></th></tr></thead><tbody>
    ${technicians.map(tech => {
      const [label,tone] = expiry(tech);
      return `<tr ${tech.id === pick.id ? 'class="picked"' : ''}><td><strong>${esc(tech.name)}</strong><small>${esc(tech.code)}</small></td>
      <td>${SERVICES[tech.skill]}<small>${tech.experience_years} 年一线经验</small></td>
      <td class="numeric">${esc(tech.valid_through)}</td><td><span class="status ${tone}"><i></i>${label}</span></td>
      <td><button class="line" data-tech="${tech.id}">证书 →</button></td></tr>`;
    }).join('')}</tbody></table></div></section>
    <aside class="panel certificate">${panelTitle('资质凭证', pick.code)}
      <div class="certificate-paper"><span>${SERVICES[pick.skill]}</span><h3>${esc(pick.name)}</h3>
      <p>${esc(pick.certificate)}</p><div>有效至 <b>${esc(pick.valid_through)}</b></div></div>
      <p class="brief muted">资质必须覆盖预约日。换发证书后，待确认方案须重新分析。</p>
      ${session.role === 'supervisor' ? `<form id="renew" class="fields single">
       <label>新证书编号<input name="certificate" minlength="4" maxlength="48" required></label>
       <label>续期截止日<input name="valid_through" type="date" min="${esc(term)}" required></label>
       <p class="form-error" role="alert"></p><button type="submit" class="primary">提交续期</button></form>` : ''}
    </aside></div>`;
  root.querySelectorAll('[data-tech]').forEach(button => button.onclick = () => {
    state.selectedTech = Number(button.dataset.tech);
    draw();
  });
  formHandler(root.querySelector('#renew'), async data => {
    await api(`/technicians/${pick.id}/qualification`,'PUT',data);
    await refresh();
    notify(`${pick.name} 的证书已续期`);
  });
}
