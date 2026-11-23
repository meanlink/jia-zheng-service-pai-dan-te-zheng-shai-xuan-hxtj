export const state = {
  token: sessionStorage.getItem('qili-session'), session: null,
  orders: [], technicians: [], plans: [], selectedOrder: null, selectedPlan: null, selectedTech: null,
};

export function setToken(token) {
  state.token = token;
  if (token) sessionStorage.setItem('qili-session', token);
  else {
    sessionStorage.removeItem('qili-session');
    Object.assign(state, {session: null, orders: [], technicians: [], plans: [], selectedOrder: null,
      selectedPlan: null, selectedTech: null});
  }
}

export const orderFor = (plan) => state.orders.find(order => order.id === plan.order_id);
export const technicianFor = (plan) => state.technicians.find(tech => tech.id === plan.technician_id);
