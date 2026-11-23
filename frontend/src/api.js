import {state, setToken} from './store.js';

export async function api(path, method = 'GET', body) {
  const token = state.token;
  const response = await fetch(`/api${path}`, {
    method,
    headers: {...(body === undefined ? {} : {'Content-Type': 'application/json'}),
              ...(token ? {Authorization: `Bearer ${token}`} : {})},
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const result = await response.json().catch(() => ({}));
  if (response.ok) return result;
  if (response.status === 401 && path !== '/login' && token === state.token) {
    setToken(null);
    window.dispatchEvent(new Event('qili-expired'));
  }
  const detail = Array.isArray(result.detail)
    ? result.detail.map(issue => `${issue.loc.at(-1)} · ${issue.msg}`).join('；') : result.detail;
  throw new Error(detail || `请求失败（${response.status}），请重试`);
}
