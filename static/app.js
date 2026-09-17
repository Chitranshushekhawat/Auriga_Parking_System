const $ = (selector) => document.querySelector(selector);
let token = localStorage.getItem('auriga_token');
let mode = 'login';
let page = 1;
const api = async (path, options = {}) => {
  const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(options.headers || {}) } });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Something went wrong');
  return data;
};
const setAuthMode = (next) => {
  mode = next;
  document.querySelectorAll('.auth-tabs button').forEach((button) => button.classList.toggle('active', button.dataset.mode === mode));
  $('#name-field').classList.toggle('hidden', mode === 'login');
  $('#auth-submit').innerHTML = mode === 'login' ? 'Sign in <span>↗</span>' : 'Create account <span>↗</span>';
};
document.querySelectorAll('.auth-tabs button').forEach((button) => button.addEventListener('click', () => setAuthMode(button.dataset.mode)));
const revealAuth = () => { $('#auth').scrollIntoView({ behavior: 'smooth' }); };
$('#hero-start').addEventListener('click', () => token ? showApp() : revealAuth());
$('#nav-login').addEventListener('click', revealAuth);
$('#auth-form').addEventListener('submit', async (event) => {
  event.preventDefault(); $('#auth-error').textContent = '';
  try {
    const payload = { email: $('#email').value, password: $('#password').value };
    if (mode === 'register') payload.name = $('#name').value;
    const result = await api(`/api/auth/${mode === 'login' ? 'login' : 'register'}`, { method: 'POST', body: JSON.stringify(payload) });
    if (mode === 'register') { setAuthMode('login'); $('#auth-error').textContent = 'Account created. Sign in to continue.'; return; }
    token = result.token; localStorage.setItem('auriga_token', token); showApp();
  } catch (error) { $('#auth-error').textContent = error.message; }
});
$('#logout').addEventListener('click', async () => { try { await api('/api/auth/logout', { method: 'POST' }); } catch (_) {} localStorage.removeItem('auriga_token'); token = null; $('#app').classList.add('hidden'); $('#auth').classList.remove('hidden'); window.scrollTo({ top: 0, behavior: 'smooth' }); });
async function showApp() {
  try { const me = await api('/api/auth/me'); if (!me.user) throw new Error('Please sign in'); $('#user-name').textContent = me.user.name.split(' ')[0]; $('#auth').classList.add('hidden'); $('#app').classList.remove('hidden'); await refresh(); $('#app').scrollIntoView({ behavior: 'smooth' }); }
  catch (_) { localStorage.removeItem('auriga_token'); token = null; }
}
async function refresh() { await Promise.all([loadDashboard(), loadSessions()]); }
async function loadDashboard() {
  const { garage, counts, active_sessions } = await api('/api/dashboard');
  const cards = [['Live vehicles', active_sessions, 'currently inside'], ['Compact', `${counts.compact?.available || 0} / ${counts.compact?.total || 0}`, 'spots available'], ['Standard', `${counts.standard?.available || 0} / ${counts.standard?.total || 0}`, 'spots available'], ['EV charger', `${counts.ev?.available || 0} / ${counts.ev?.total || 0}`, 'spots available']];
  $('#metrics').innerHTML = cards.map(([label, value, note]) => `<div class="metric"><label>${label}</label><strong>${value}</strong><small>${note}</small></div>`).join('');
}
async function loadSessions() {
  const search = encodeURIComponent($('#search').value); const sort = $('#sort').value;
  const { sessions, pagination } = await api(`/api/sessions?search=${search}&sort=${sort}&page=${page}&page_size=8`);
  $('#total-label').textContent = `${pagination.total} total`; $('#page-label').textContent = `${pagination.page} / ${pagination.pages}`; $('#prev').disabled = page <= 1; $('#next').disabled = page >= pagination.pages;
  $('#session-rows').innerHTML = sessions.length ? sessions.map((session) => `<tr><td><span class="plate-name">${session.plate}</span><span class="sub">${session.driver_name}</span></td><td><strong>${session.spot_number}</strong><span class="sub">${session.vehicle_type}</span></td><td>${new Date(session.checked_in_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</td><td><span class="tag ${session.status === 'completed' ? 'done' : ''}">${session.status === 'active' ? 'Inside' : `£${session.fee}`}</span></td><td>${session.status === 'active' ? `<button class="checkout" data-id="${session.id}">Check out →</button>` : ''}</td></tr>`).join('') : '<tr><td colspan="5">No vehicles match that search.</td></tr>';
  document.querySelectorAll('.checkout').forEach((button) => button.addEventListener('click', () => checkOut(button.dataset.id)));
}
async function checkOut(id) { try { const result = await api(`/api/sessions/${id}/check-out`, { method: 'POST', body: '{}' }); alert(`Vehicle checked out. Fee: £${result.fee} (${result.hours_charged} hour${result.hours_charged === 1 ? '' : 's'} charged)`); await refresh(); } catch (error) { alert(error.message); } }
$('#checkin-form').addEventListener('submit', async (event) => { event.preventDefault(); $('#checkin-error').textContent = ''; try { const result = await api('/api/sessions/check-in', { method: 'POST', body: JSON.stringify({ plate: $('#plate').value, driver_name: $('#driver').value, vehicle_type: $('#vehicle').value }) }); $('#checkin-form').reset(); alert(`Assigned ${result.session.spot_number} to ${result.session.plate}`); await refresh(); } catch (error) { $('#checkin-error').textContent = error.message; } });
let searchTimer; $('#search').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { page = 1; loadSessions(); }, 250); }); $('#sort').addEventListener('change', () => { page = 1; loadSessions(); }); $('#prev').addEventListener('click', () => { page -= 1; loadSessions(); }); $('#next').addEventListener('click', () => { page += 1; loadSessions(); });
if (token) showApp();
