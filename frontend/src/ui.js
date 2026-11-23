import {FEATURES, PLAN_STATUS} from './domain.js';

export const esc = (value) => String(value ?? '').replace(/[&<>"']/g, x => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[x]));
export const signed = (number, digits = 0) => (number > 0 ? '+' : '') + Number(number).toFixed(digits);
export const optionTags = (labels) => Object.entries(labels).map(([key, label]) =>
  `<option value="${esc(key)}">${esc(label)}</option>`).join('');

export function status(key) {
  const tone = ['review_pre', 'review_post', 'failed'].includes(key) ? 'warn' :
    ['closed', 'confirmed', 'reviewed'].includes(key) ? 'good' : 'plain';
  return `<span class="status ${tone}"><i></i>${esc(PLAN_STATUS[key] || '未试算')}</span>`;
}

export function empty(title, desc) {
  return `<div class="empty"><strong>${esc(title)}</strong><p>${esc(desc)}</p></div>`;
}

export function panelTitle(text, meta = '') {
  return `<header class="panel-title"><h2>${esc(text)}</h2>${meta ? `<span>${esc(meta)}</span>` : ''}</header>`;
}

let noticeTimer;
export function notify(text, error = false) {
  const area = document.querySelector('#notice');
  area.textContent = text;
  area.className = `notice visible ${error ? 'error' : ''}`;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => area.classList.remove('visible'), 4800);
}

export function formHandler(form, callback) {
  if (!form) return;
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const submit = form.querySelector('button[type=submit]');
    const message = form.querySelector('[role=alert]');
    if (message) message.textContent = '';
    submit.disabled = true;
    try {
      await callback(Object.fromEntries(new FormData(form)));
    } catch (error) {
      if (message) message.textContent = error.message;
      else notify(error.message, true);
    } finally {
      submit.disabled = false;
    }
  });
}

export function featureTable(analysis) {
  return `<div class="table-scroll"><table class="evidence-table"><thead><tr>
    <th>特征 / 本单</th><th>筛选结果</th><th>回归系数</th><th>本单工时贡献</th></tr></thead><tbody>
    ${analysis.features.map(feature => {
      const [name, unit] = FEATURES[feature.key];
      const value = feature.key === 'supplies' ? (feature.value ? '有' : '无') : feature.value;
      const width = Math.min(Math.abs(feature.contribution) * 2, 112);
      return `<tr><td><strong>${name}</strong> <span class="muted">${esc(value)}</span>
        ${feature.outside_history ? '<small class="flag">超出训练范围</small>' : ''}</td>
        <td>${feature.selected ? '<span class="tag kept">保留</span>' : '<span class="tag">剔除</span>'}</td>
        <td>${feature.selected ? `${signed(feature.coefficient, 2)} 分钟 <small>${unit}</small>` : '—'}</td>
        <td class="contribution"><span class="bar ${feature.contribution < 0 ? 'negative' : ''}" style="--w:${width}px"></span>
          <b>${signed(feature.contribution, 1)}</b></td></tr>`;
    }).join('')}
  </tbody></table></div>`;
}
