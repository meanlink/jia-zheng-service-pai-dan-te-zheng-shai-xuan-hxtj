export const SERVICES = {deep_clean: '深度保洁', appliance_clean: '家电清洗'};
export const SLOTS = {am: '上午', pm: '下午', evening: '晚间'};
export const ROLES = {intake: '客服受理', dispatcher: '值班调度', supervisor: '运营主管'};
export const ORDER_STATUS = {received: '待派单', assigned: '已派单', followed_up: '已回访'};
export const PLAN_STATUS = {
  queued: '分析排队', analyzed: '特征已就绪', failed: '分析失败', trial: '试算就绪',
  review_pre: '派单前待复核', reviewed: '复核通过', confirmed: '已确认',
  review_post: '回访偏差待复核', closed: '已结案',
};
export const FEATURES = {
  area_m2: ['作业面积', '每平方米'], dirt_level: ['污损等级', '每级'],
  obstacles: ['障碍物', '每处'], supplies: ['现场备料', '无 → 有'], experience_years: ['技师经验', '每年'],
};
export const EVENTS = {
  visit_contact: '上门联络', order_received: '订单受理', analysis_queued: '提交特征分析', analysis_ready: '特征分析完成',
  analysis_failed: '分析未完成', dispatch_trial: '生成派单试算', dispatch_confirmed: '调度确认',
  access_recorded: '入户核验登记', scope_proposed: '提交范围补测', scope_decided: '完成范围复核',
  scenario_saved: '保存工时假设对照', handover_issued: '发出上门交接', handover_arrival: '登记到场回执',
  pre_dispatch_reviewed: '派单前复核', followup_recorded: '回访登记', post_followup_reviewed: '复盘结案',
};
