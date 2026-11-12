'use strict';
const $ = id => document.getElementById(id);
let config, companion, hosting, pairTimer, qrUrl, pairUntil, pairingEnabled = false, pairingBusy = false;
function requestId() {
  if (crypto.randomUUID) return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16)); bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
  const h = Array.from(bytes,x=>x.toString(16).padStart(2,'0')).join('');
  return [h.slice(0,8),h.slice(8,12),h.slice(12,16),h.slice(16,20),h.slice(20)].join('-');
}
function message(text, error = false) { $('message').textContent = text; $('message').classList.toggle('error', error); }
async function request(path, method = 'GET', value) {
  const response = await fetch(path, {method, cache:'no-store', credentials:'same-origin', headers:{'X-TimePRO-Setup':'1', ...(method === 'GET' ? {} : {'Content-Type':'application/json'})}, ...(method === 'GET' ? {} : {body:JSON.stringify(value || {})})});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'The request did not finish. Please retry.');
  return data;
}
function busyForm(id, action) {
  $(id).addEventListener('submit', async event => {event.preventDefault(); const button = $(id).querySelector('button'); button.disabled = true; try {await action();} catch(error) {message(error.message, true);} finally {button.disabled = false;}});
}
function providerVisibility() {
  $('provider-details').hidden = ['builtin','manual'].includes($('provider').value);
  $('builtin-note').hidden = $('provider').value !== 'builtin';
}
$('provider').addEventListener('change', providerVisibility);
$('test-provider').addEventListener('click', async () => {
  $('test-provider').disabled = true; message('Testing the saved provider…');
  try {await request('setup/provider/test','POST'); message('The saved provider understood the test. No task was added.');}
  catch(error) {message(error.message,true);} finally {$('test-provider').disabled = false;}
});
busyForm('provider-form', async () => {
  const choice = $('provider').value;
  if (choice === 'builtin' && hosting.model.state !== 'ready') throw new Error('The built-in model is not ready. Enable it in add-on Configuration, restart, then wait for the download.');
  const payload = choice === 'builtin' ? {provider:'open_ai_compatible', endpoint:'http://127.0.0.1:11435/v1',model:'timepro-local',allow_local_http:true,clear_api_key:true} : {provider:choice,endpoint:choice === 'manual' ? 'http://127.0.0.1:11434' : $('endpoint').value.trim(),model:choice === 'manual' ? '' : $('model').value.trim(),allow_local_http:$('local-http').checked};
  if ($('api-key').value && choice !== 'builtin') payload.api_key = $('api-key').value;
  try {config = await request('setup/provider','PUT',payload); message('Provider saved.');} finally {$('api-key').value = '';}
});
busyForm('calendar-form', async () => {
  const payload = {base_url:$('calendar-url').value.trim(),username:$('calendar-user').value.trim()};
  if ($('calendar-password').value) payload.password = $('calendar-password').value;
  try {config = await request('setup/calendar','PUT',payload);} finally {$('calendar-password').value = '';}
  const result = await request('setup/calendars','POST');
  $('calendars').replaceChildren();
  for (const calendar of result.calendars) {
    const row = document.createElement('div'); row.className = 'row';
    const title = document.createElement('strong'); title.textContent = calendar.display_name;
    const label = document.createElement('label'); label.textContent = 'Use this calendar as';
    const kind = document.createElement('select'); for (const [value, text] of [['fixed','Classes & appointments'],['deadlines','Homework & exam deadlines']]) {const option = document.createElement('option'); option.value = value; option.textContent = text; kind.append(option);} label.append(kind);
    const sync = document.createElement('button'); sync.type = 'button'; sync.textContent = 'Sync calendar';
    sync.addEventListener('click', async () => {sync.disabled = true; try {await request('setup/sync','POST',{href:calendar.href,kind:kind.value}); message(calendar.display_name + ' synced.'); sync.textContent = 'Sync again';} catch(error) {message(error.message,true);} finally {sync.disabled = false;}});
    row.append(title,label,sync); $('calendars').append(row);
  }
  message(result.calendars.length ? 'Calendars found. Choose a purpose, then sync each one.' : 'Connected; no calendars were returned.');
});
busyForm('language-form', async () => {
  companion = await request('setup/state');
  await request('setup/language','PUT',{schedule_language:$('language').value, expected_revision:companion.preferences.revision, request_id:requestId()});
  message('Schedule language saved.');
});
function clearQr() {if (qrUrl) URL.revokeObjectURL(qrUrl); qrUrl = null; $('qr').removeAttribute('src'); $('pairing').hidden = true;}
function stopPairing() {pairingEnabled = false; clearInterval(pairTimer); pairTimer = null; clearQr(); $('stop-pair').hidden = true;}
async function newCode() {
  if (!pairingEnabled || pairingBusy || document.hidden) return;
  pairingBusy = true;
  try {
    const ticket = await request('setup/pair','POST');
    if (!pairingEnabled || document.hidden) return;
    clearQr(); qrUrl = URL.createObjectURL(new Blob([ticket.qr_svg],{type:'image/svg+xml'}));
    $('qr').src = qrUrl; $('pairing').hidden = false; $('stop-pair').hidden = false; pairUntil = Date.parse(ticket.expires_at);
    $('expires').textContent = 'Private code · valid for two minutes';
  } catch(error) {stopPairing(); message(error.message,true);} finally {pairingBusy = false;}
}
$('pair').addEventListener('click', async () => {
  stopPairing(); pairingEnabled = true; await newCode();
  const stopAt = Date.now() + 15 * 60 * 1000;
  if (pairingEnabled) pairTimer = setInterval(() => {
    if (Date.now() >= stopAt) {stopPairing(); message('Pairing display closed. Tap Pair a phone for a new code.'); return;}
    const remaining = Math.max(0,Math.ceil((pairUntil-Date.now())/1000));
    $('expires').textContent = 'Private code · ' + remaining + ' seconds remaining';
    if (remaining < 30) newCode();
  },1000);
});
$('stop-pair').addEventListener('click', stopPairing);
document.addEventListener('visibilitychange', () => {if (document.hidden) stopPairing();});
window.addEventListener('pagehide', stopPairing);
async function devices() {
  const data = await request('setup/devices'); $('devices').replaceChildren();
  for (const device of data.devices) {
    const row = document.createElement('div'); row.className = 'row';
    const name = document.createElement('p'); name.textContent = device.name;
    const revoke = document.createElement('button'); revoke.type = 'button'; revoke.className = 'secondary'; revoke.textContent = 'Disconnect';
    revoke.addEventListener('click', async () => {if (!confirm('Disconnect ' + device.name + '? It will need a new pairing code.')) return; try {await request('setup/devices/' + device.id,'DELETE'); await devices(); message('Phone disconnected.');} catch(error) {message(error.message,true);}});
    row.append(name,revoke); $('devices').append(row);
  }
  if (!data.devices.length) $('devices').textContent = 'No phones paired yet.';
}
async function refreshHosting() {
  hosting = await request('setup/status');
  const model = hosting.model;
  $('model-state').textContent = model.state === 'downloading' ? 'Downloading · ' + model.percent + '%' : ({ready:'Ready',disabled:'Off',starting:'Starting',checking:'Checking weights',error:'Needs attention'}[model.state] || 'Starting');
  $('phone-info').textContent = hosting.phone_access === 'disabled' ? 'Before pairing, set phone_access and public_url in the add-on Configuration tab. Use a certificate from /ssl or your existing HTTPS reverse proxy. HA ingress is for this setup page.' : 'Your phone connects to ' + hosting.public_url + '. Make sure it is reachable with a valid HTTPS certificate before scanning.';
  $('pair').disabled = hosting.phone_access === 'disabled';
  const note = {ready:'Your local model is ready. Requests stay on this Home Assistant host.',downloading:'Downloading the verified local model: '+model.percent+'%. The planner remains available.',checking:'Checking your cached model. No new download is needed if the checksum matches.',starting:'Preparing the local model. This can take a moment.'};
  $('builtin-note').textContent = model.state === 'error' ? model.message : (note[model.state] || 'Enable built_in_model in the add-on Configuration tab, then restart. The first download is about 1.1 GB. Allow at least 2.5 GB of free RAM beyond Home Assistant.');
}
async function start() {
  try {
    config = await request('setup/config');
    $('planner').textContent = 'Running'; $('timezone').textContent = config.preferences.timezone;
    const provider = config.provider;
    $('provider').value = provider.provider === 'open_ai_compatible' && provider.endpoint === 'http://127.0.0.1:11435/v1' ? 'builtin' : provider.provider;
    $('endpoint').value = provider.endpoint; $('model').value = provider.model; $('local-http').checked = provider.allow_local_http;
    $('calendar-url').value = config.calendar.base_url; $('calendar-user').value = config.calendar.username;
    companion = await request('setup/state'); $('language').value = companion.preferences.schedule_language;
    await refreshHosting(); providerVisibility(); await devices(); message('Your planner is running. Finish the connections below.');
  } catch(error) {message(error.message,true); $('planner').textContent = 'Retry needed';}
}
start();
setInterval(() => {if (!document.hidden) refreshHosting().catch(() => {});},15000);
