import {api} from './api.js';
import {ROLES} from './domain.js';
import {setToken,state} from './store.js';
import {esc, formHandler, notify} from './ui.js';
import {handoverPage} from './pages/handover.js';
import {readinessPage} from './pages/readiness.js';
import {scenariosPage} from './pages/scenarios.js';
import {featuresPage} from './pages/features.js';
import {ordersPage} from './pages/orders.js';
import {reviewPage} from './pages/review.js';
import {timeOffPage, visitContactPage} from './pages/scheduling.js';
import {techniciansPage} from './pages/technicians.js';

const routes = {
  orders: ['订单受理', '核对上门条件，登记预约与客服预估。', ordersPage],
  technicians: ['技师资质', '查验证书及上门服务覆盖情况。', techniciansPage],
  'time-off': ['技师停工', '登记请假和停工时段，避免与派工预约冲突。', timeOffPage],
  'visit-contacts': ['上门确认与改期', '处理客户确认及待派工单的预约变更。', visitContactPage],
  readiness: ['派前核验', '核对入户安排和客户补测范围，解除派单暂停。', readinessPage],
  features: ['特征工作台', '用历史完单筛出工时因素，核对本单预测。', featuresPage],
  scenarios: ['工时假设对照', '比较客户补充条件对工时预测的影响。', scenariosPage],
  handover: ['上门交接', '发出现场交接单并记录技师到场结果。', handoverPage],
  review: ['派单复盘', '确认预约，登记实绩，复核超出阈值的工时偏差。', reviewPage],
};
const icons = {
  orders: '<path d="M5 3h11l3 3v15H5z M8 9h8 M8 13h8 M8 17h5"/>',
  technicians: '<path d="M4 5h16v14H4z M7 15l2 2 4-4 M14 9h3"/><circle cx="9" cy="10" r="2"/>',
  'time-off': '<path d="M4 6h16v14H4z M4 10h16 M8 4v4 M16 4v4 M9 13l6 4 M15 13l-6 4"/>',
  'visit-contacts': '<path d="M4 5h16v11H9l-5 4z M8 9h8 M8 12h6"/>',
  readiness: '<path d="M5 4h14v16H5z M8 9l1.5 1.5L12 8 M8 15l1.5 1.5L12 14 M14 9h2 M14 15h2"/>',
  scenarios: '<path d="M4 4v16h16 M8 15l4-5 3 2 5-6 M8 18l5-3 3 1 4-3"/>',
  handover: '<path d="M3 11l9-7 9 7 M6 10v10h12V10 M9 15h6m-2-2 2 2-2 2"/>',
  features: '<path d="M4 6h16 M4 12h16 M4 18h16 M8 4v4 M16 10v4 M12 16v4"/>',
  review: '<path d="M12 4a8 8 0 1 1-8 8 M7 4H4v3 M12 8v5l3 2"/>',
};
const icon = (key) => `<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5">${icons[key]}</svg>`;
const brand = `<div class="brand"><div class="mark" aria-hidden="true">栖</div><div><b>栖里家服</b><span>派单工作台</span></div></div>`;
const root = document.querySelector('#app');
let revision = 0;
let waitingTimer;

function loginView() {
  root.innerHTML = `<main class="login"><section class="login-aside">${brand}
    <div class="login-story"><h1>上门服务<br>派单工作台</h1><p>受理、资质核验、工时试算和回访。</p></div>
    <div class="house-art" aria-hidden="true"></div></section>
    <section class="login-form"> <header><h2>登录工作台</h2><p>使用你的岗位账号登录。</p></header>
    <form id="login" class="fields single"><label>账号<input name="username" autocomplete="username" required></label>
      <label>密码<input name="password" type="password" autocomplete="current-password" required></label>
      <p class="form-error" role="alert"></p><button type="submit" class="primary">进入工作台 →</button></form>
    <details class="demo"><summary>演示账号</summary><p>客服 intake · 调度 dispatch · 主管 lead</p><p>密码 Qili-demo-48</p></details></section></main>`;
  formHandler(root.querySelector('#login'), async credentials => {
    const {token} = await api('/login','POST',credentials);
    setToken(token);
    await refresh();
  });
}

function draw() {
  clearTimeout(waitingTimer);
  if (!state.token) { loginView(); return; }
  if (!state.session) { root.innerHTML = '<p class="loading">正在连接派单工作台…</p>'; return; }
  const rawKey = location.hash.slice(1);
  const key = Object.hasOwn(routes,rawKey) ? rawKey : 'orders';
  const [title, subtitle, page] = routes[key];
  root.innerHTML = `<div class="workspace"><aside class="sidebar">${brand}<nav aria-label="业务导航">
    ${Object.entries(routes).map(([id,[label]]) => `<a href="#${id}" ${key === id ? 'aria-current="page"' : ''}>${icon(id)}${label}</a>`).join('')}
    </nav><div class="identity"><b>${esc(state.session.name)}</b><span>${ROLES[state.session.role]}</span><button class="line" id="logout">退出</button></div></aside>
    <main class="main"><header class="heading"><div><h1>${title}</h1><p>${subtitle}</p></div>
    <div class="date"><span>上海业务日</span><b>${esc(state.session.business_date)}</b></div></header><div id="page"></div></main></div>`;
  root.querySelector('#logout').onclick = () => {
    revision++;
    setToken(null);
    history.replaceState(null, '', location.pathname + location.search);
    draw();
  };
  page(root.querySelector('#page'), refresh, draw);
  if (key === 'features' && root.querySelector('.pending')) {
    waitingTimer = setTimeout(() => refresh().catch(error => notify(error.message, true)), 1100);
  }
}

async function refresh() {
  const id = ++revision;
  const [session, orders, technicians, plans] = await Promise.all([
    api('/session'), api('/orders'), api('/technicians'), api('/plans'),
  ]);
  if (id !== revision || !state.token) return;
  Object.assign(state,{session,orders,technicians,plans});
  draw();
}

window.addEventListener('hashchange', draw);
window.addEventListener('qili-expired', () => { revision++; draw(); notify('登录已过期，请重新登录', true); });
draw();
if (state.token) refresh().catch(error => {
  if (!state.token) return;
  root.innerHTML = '<main class="loading"><p>工作台暂不可用</p><button class="primary" id="retry">重新连接</button></main>';
  root.querySelector('#retry').onclick = () => location.reload();
  notify(error.message, true);
});
