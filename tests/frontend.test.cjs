const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const source = fs.readFileSync(
  path.join(__dirname, "../server/static/app.js"),
  "utf8",
);
function sandbox() {
  const elements = new Map();
  const element = (selector) => {
    if (!elements.has(selector))
      elements.set(selector, {
        innerHTML: "",
        textContent: "",
        value: "",
        open: false,
        hidden: false,
        classList: { toggle() {}, add() {}, remove() {} },
        addEventListener() {},
        replaceChildren() {
          this.innerHTML = "";
        },
        focus() {},
        matches() {
          return false;
        },
        showModal() {
          this.open = true;
        },
        close() {
          this.open = false;
        },
        querySelector: element,
      });
    return elements.get(selector);
  };
  const context = vm.createContext({
    document: {
      querySelector: element,
      querySelectorAll: () => [],
      addEventListener() {},
      title: "",
    },
    window: { addEventListener() {}, confirm: () => true },
    history: { replaceState() {} },
    location: { hash: "", origin: "https://status.example.com" },
    navigator: {},
    setTimeout: () => 0,
    clearTimeout() {},
    AbortSignal,
    URL,
    Blob,
    fetch: async () => ({ ok: true, json: async () => ({}) }),
    console,
  });
  vm.runInContext(source, context);
  return { context, elements, run: (code) => vm.runInContext(code, context) };
}
const record = (id, name = id) => ({
  machine_id: id,
  user_id: "1000",
  status: "online",
  age_seconds: 5,
  report_keys: [],
  settings: {
    display_name: name,
    notes: "",
    enabled: true,
    report_interval: null,
  },
  report: {
    hostname: id,
    cpu_usage: 0.5,
    ram_usage: 0.6,
    created_at: "2026-01-01T00:00:00Z",
  },
});
const fixture = (clients) => ({
  settings: {
    server_name: "MXStatus",
    refresh_interval: 15,
    offline_after_seconds: 300,
    default_report_interval: 10,
    max_machines: 10000,
    accept_new_clients: true,
  },
  clients,
  report_keys: [],
  view_groups: [],
  users: ["1000"],
  user_id: "1000",
  runtime: {
    persistent: true,
    python: "3.12",
    version: "0.1",
    uptime_seconds: 3600,
    cors_origins: [],
  },
});

// These are isolated rendering/transport unit tests, not a substitute for browser QA.
test("untrusted HTML and attribute delimiters are escaped", () => {
  const { run } = sandbox();
  assert.equal(
    run(`escapeHTML('<img src=x onerror="boom"> &')`),
    "&lt;img src=x onerror=&quot;boom&quot;&gt; &amp;",
  );
});

test("fleet table escapes reported names and limits rows to 50", () => {
  const { run, elements } = sandbox();
  const clients = Array.from({ length: 123 }, (_, index) =>
    record(
      `m${index}`,
      index === 0 ? '<img src=x onerror="alert(1)">' : `Client ${index}`,
    ),
  );
  run(`data = ${JSON.stringify(fixture(clients))}; renderClientsTable();`);
  const html = elements.get("#clients-table").innerHTML;
  assert.ok(!html.includes("<img src=x"));
  assert.ok(html.includes("&lt;img"));
  assert.equal((html.match(/<tr>/g) || []).length, 51); // Header plus 50 rows.
  assert.ok(html.includes("1–50 of 123"));
  run("clientPage=3; renderClientsTable();");
  assert.ok(
    elements.get("#clients-table").innerHTML.includes("101–123 of 123"),
  );
});

test("search and offline filter handle waiting clients", () => {
  const { run, elements } = sandbox();
  const clients = [
    record("m1", "Research GPU"),
    {
      ...record("m2", "Storage"),
      status: "waiting",
      report: null,
      age_seconds: null,
    },
  ];
  run(
    `data = ${JSON.stringify(fixture(clients))}; query='research'; renderClientsTable();`,
  );
  assert.ok(elements.get("#clients-table").innerHTML.includes("Research GPU"));
  assert.ok(!elements.get("#clients-table").innerHTML.includes(">Storage<"));
  run("query='';filter='offline';renderClientsTable();");
  assert.ok(elements.get("#clients-table").innerHTML.includes("Storage"));
  assert.ok(
    !elements.get("#clients-table").innerHTML.includes(">Research GPU<"),
  );
});

test("empty fleet provides a connection action", () => {
  const { run, elements } = sandbox();
  run(`data=${JSON.stringify(fixture([]))};renderClientsTable();`);
  assert.ok(
    elements.get("#clients-table").innerHTML.includes('data-action="connect"'),
  );
});

test("view names, descriptions, and settings values cannot inject markup", () => {
  const { run } = sandbox();
  const state = fixture([]);
  state.settings.server_name = '\" autofocus onfocus=alert(1) x=\"';
  state.view_groups = [
    {
      view_key: "A".repeat(32),
      view_name: "<script>alert(1)</script>",
      view_desc: "<iframe src=evil>",
      view_enabled: true,
      view_machines: [],
    },
  ];
  run(`data=${JSON.stringify(state)};`);
  const views = run("viewsPage()");
  assert.ok(!views.includes("<script>"));
  assert.ok(!views.includes("<iframe"));
  const settings = run("settingsPage()");
  assert.ok(settings.includes('value="&quot; autofocus'));
});

test("client notes escape closing textarea injection", () => {
  const { run, elements } = sandbox();
  const client = record("m1");
  client.settings.notes = "</textarea><script>alert(1)</script>";
  run(`data=${JSON.stringify(fixture([client]))};editClient(data.clients[0]);`);
  const html = elements.get("#modal-content").innerHTML;
  assert.ok(!html.includes("<script>"));
  assert.ok(html.includes("&lt;/textarea&gt;"));
});

test("API puts bearer credentials in headers and disables caching", async () => {
  const { run, context } = sandbox();
  let request;
  context.fetch = async (url, options) => {
    request = { url, options };
    return { ok: true, json: async () => ({ msg: "OK" }) };
  };
  await run(
    'token="test-admin-token";api("keys/delete",{report_key:"REPORTKEY"})',
  );
  assert.equal(request.url, "/admin/api/keys/delete");
  assert.equal(
    request.options.headers.Authorization,
    "Bearer test-admin-token",
  );
  assert.equal(request.options.cache, "no-store");
  assert.equal(request.options.credentials, "omit");
  assert.deepEqual(JSON.parse(request.options.body), {
    report_key: "REPORTKEY",
  });
});

test("sign out clears credentials, data, and private dialog content", () => {
  const { run, elements } = sandbox();
  run(
    `data=${JSON.stringify(fixture([record("m1")]))};token="secret";openModal("Key","private key");signOut();`,
  );
  assert.equal(run("token"), "");
  assert.equal(run("data"), null);
  assert.equal(elements.get("#modal-content").innerHTML, "");
  assert.equal(elements.get("#page-content").innerHTML, "");
  assert.equal(elements.get("#console").hidden, true);
});

test("late refresh response cannot restore data after sign out", async () => {
  const { run, context, elements } = sandbox();
  let resolve;
  context.fetch = () =>
    new Promise((done) => {
      resolve = done;
    });
  run(`token="secret";data=${JSON.stringify(fixture([]))};`);
  const pending = run("refresh()");
  run("signOut()");
  resolve({ ok: true, json: async () => fixture([record("private")]) });
  await pending;
  assert.equal(run("data"), null);
  assert.equal(elements.get("#console").hidden, true);
});

test("late key creation does not expose a secret after sign out", async () => {
  const { run, context, elements } = sandbox();
  let resolve;
  context.fetch = () =>
    new Promise((done) => {
      resolve = done;
    });
  run(`token="secret";data=${JSON.stringify(fixture([]))};`);
  const pending = run('mutation("keys",{},"Created")');
  run("signOut()");
  resolve({ ok: true, json: async () => ({ report_key: "PRIVATE" }) });
  await assert.rejects(pending, /session has ended/);
  assert.equal(elements.get("#modal-content").innerHTML, "");
});

test("an older poll cannot overwrite a forced refresh after a save", async () => {
  const { run, context } = sandbox();
  const callbacks = [];
  context.fetch = () => new Promise((resolve) => callbacks.push(resolve));
  run(`token="secret";data=${JSON.stringify(fixture([]))};`);
  const older = run("refresh(false)");
  const newer = run("refresh(false,true)");
  callbacks[1]({ ok: true, json: async () => fixture([record("latest")]) });
  await newer;
  callbacks[0]({ ok: true, json: async () => fixture([]) });
  await older;
  assert.equal(run("data.clients[0].machine_id"), "latest");
});
