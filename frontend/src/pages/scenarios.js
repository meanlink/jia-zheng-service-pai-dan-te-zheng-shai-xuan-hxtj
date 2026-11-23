import {api} from '../api.js';
import {FEATURES} from '../domain.js';
import {fieldForm, mountFieldWorkspace, scopeFields, scopePayload} from '../field-workspace.js';
import {esc, signed} from '../ui.js';

function featureValue(key, value) {
  return key === 'supplies' ? (value ? '有' : '无') : esc(value);
}

function comparisonCard(row) {
  const c = row.comparison;
  return `<article class="panel field-result"><div class="panel-title"><h2>工时对照 #${row.id}</h2>
    <span class="tag ${row.current ? 'kept' : 'field-warn'}">${row.current ? '当前模型' : '历史模型'}</span></div>
    <div class="field-body"><div class="field-metrics"><div><small>原预测</small><strong>${c.baseline_minutes} 分</strong></div>
      <div><small>假设预测</small><strong>${c.scenario_minutes} 分</strong></div>
      <div><small>预测差值</small><strong>${signed(c.delta_minutes)} 分</strong></div></div>
      <p>${esc(row.note)}</p><p class="muted">模型记录 #${row.analysis_event_id} · 验证 MAE ${c.holdout_mae} 分 · 样本 ${esc(c.history_checksum.slice(0,12))}</p></div>
    <div class="table-scroll"><table><thead><tr><th>特征</th><th>原值 → 假设</th><th>模型结果</th><th>工时贡献变化</th></tr></thead><tbody>
      ${c.features.map(f => `<tr><td>${FEATURES[f.key][0]}</td><td>${featureValue(f.key,f.before)} → ${featureValue(f.key,f.after)}
        ${f.outside_history ? '<small class="flag">超出训练范围</small>' : ''}</td><td>${f.selected ? '保留' : '剔除'}</td>
        <td>${signed(f.contribution_delta,1)} 分</td></tr>`).join('')}</tbody></table></div></article>`;
}

export function scenariosPage(root, refresh) {
  mountFieldWorkspace(root, {
    refresh,
    preferred: order => order.code === 'QL-1105',
    render: (data, session) => `<div class="field-columns scenario-layout"><section class="panel"><div class="panel-title"><h2>调整工时假设</h2></div>
      <div class="field-body"><p>按同一版入选特征和回归系数计算，保留两组工时及逐项贡献。</p>
      ${!data.can_compare ? '<p class="field-callout">先在特征工作台完成待派订单的分析，再建立对照。</p>' : ''}</div>
      ${data.can_compare && session.role === 'dispatcher' ? fieldForm('scenario-save', scopeFields(data.order), '对照目的', '保存工时对照') : ''}
      </section><div class="field-stack" id="scenario-results">${data.scenarios.map(comparisonCard).join('') ||
        '<div class="panel field-body"><p class="muted">该工单暂无保存的工时对照。</p></div>'}</div></div>
      <div class="field-links"><a class="line" href="#features">返回特征工作台 →</a><a class="line" href="#readiness">提交实际范围到派前核验 →</a></div>`,
    bind: (_root, data, action) => action('#scenario-save', values =>
      api(`/plans/${data.plan_id}/scenarios`, 'POST', {...scopePayload(values), analysis_event_id: data.analysis_event_id}), '已保存工时对照'),
  });
}
