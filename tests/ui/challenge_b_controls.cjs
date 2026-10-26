const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const html = fs.readFileSync(process.argv[2], 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1].replace('boot();', '');
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    value: '', textContent: '', innerHTML: '', style: {}, disabled: false,
    classList: {add() {}, remove() {}, toggle() {}}, addEventListener() {}, focus() {},
  });
  return elements.get(id);
}
const storage = new Map();
let approved = false, failed = false;
const calls = [];
const chat = (id, ready = false) => ({
  thread_id: id, execution: 'offline', timeline: ready ? [{kind: 'user', content: 'Old chat'}] : [],
  usage: {actual_input_tokens: 0, actual_output_tokens: 0, requests: 0, last: null},
  context: {state: ready ? 'ready' : 'not_loaded', loaded_estimated_tokens: ready ? 2600 : 0,
    estimated_input_tokens: ready ? 2600 : 2260}, model: 'offline',
});
const context = vm.createContext({
  console, URLSearchParams, document: {getElementById: element, querySelectorAll: () => []},
  localStorage: {getItem: k => storage.get(k) || null, setItem: (k, v) => storage.set(k, v)},
  location: {pathname: '/challenge-b', search: ''}, history: {replaceState() {}},
  confirm: () => approved,
  fetch: async (url, options) => {
    calls.push({url, body: JSON.parse(options?.body || 'null')});
    const fresh = chat(url.endsWith('/reset') ? 'bchat-000000000002' : 'bchat-000000000001');
    return {ok: !failed, json: async () => failed ? {detail: 'Test error'} :
      url.endsWith('/reset') ? {deleted: 2, chat: fresh} : fresh};
  },
});
vm.runInContext(script, context);
const run = source => vm.runInContext(source, context);
const setChat = value => run('current=' + JSON.stringify(value));

(async () => {
  setChat(chat('bchat-000000000001'));
  run('render()');
  assert.match(element('context-value').textContent, /^0 \/ /);
  assert.match(element('context-state').textContent, /chưa nạp/);
  assert.match(element('context-note').textContent, /2\.260/); // Forecast must not pretend first input is free.
  assert.equal(element('context-fill').style.width, '0%');
  assert.equal(element('compact-btn').disabled, true);

  setChat(chat('bchat-000000000001', true));
  run('render()');
  assert.match(element('context-value').textContent, /^2\.600/);
  assert.match(element('context-state').textContent, /ước lượng lượt kế/);
  await run('resetAll()');
  await run('resetContext()');
  assert.equal(calls.length, 0); // Cancel must not write anything.

  approved = true;
  await run('resetContext()');
  assert.equal(calls[0].url, '/api/challenge-b/chat/reset-context');
  assert.equal(calls[0].body.thread_id, 'bchat-000000000001');
  assert.match(element('context-value').textContent, /^0 \/ /);

  element('input').value = 'Old draft';
  await run('resetAll()');
  assert.equal(calls[1].url, '/api/challenge-b/reset');
  assert.equal(run('current.thread_id'), 'bchat-000000000002');
  assert.equal(element('input').value, '');
  assert.match(element('context-value').textContent, /^0 \/ /);
  assert.match(element('notice').textContent, /2/);

  const count = calls.length;
  run('busy=true');
  await run('resetAll()');
  await run('resetContext()');
  assert.equal(calls.length, count);
  run('busy=false');
  failed = true;
  await run('resetAll()');
  assert.equal(element('notice').style.display, 'none');
  assert.equal(element('error').textContent, 'Test error');
  assert(calls.every(c => c.url.startsWith('/api/challenge-b/')));
  console.log('Page meter, forecasts, reset controls and error handling: PASS');
})().catch(error => {console.error(error); process.exitCode = 1;});
