"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const escapeHTML = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        char
      ],
  );
const e = escapeHTML;
const paths = {
  servers:
    '<rect x="3" y="3" width="18" height="7" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><path d="M7 6.5h.01M7 17.5h.01M12 6.5h5M12 17.5h5"/>',
  server:
    '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 17h.01"/>',
  key: '<circle cx="8" cy="8" r="5"/><path d="m12 12 9 9m-4-4 3-3m-6 0 3-3"/>',
  layers:
    '<path d="m12 3 10 6-10 6L2 9l10-6Zm-10 12 10 6 10-6M2 12l10 6 10-6"/>',
  settings:
    '<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="15" cy="17" r="3"/>',
  logout: '<path d="M9 4H4v16h5m6-12 4 4-4 4m-6-4h10"/>',
  refresh:
    '<path d="M20 8a8 8 0 0 0-14-3L3 8m0-5v5h5M4 16a8 8 0 0 0 14 3l3-3m0 5v-5h-5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  search: '<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/>',
  arrow: '<path d="m9 5 7 7-7 7"/>',
  copy: '<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M15 4H5a2 2 0 0 0-2 2v10"/>',
  edit: '<path d="m15 4 5 5M4 20l5-1L21 7l-4-4L5 15l-1 5Z"/>',
  trash: '<path d="M3 6h18M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
  eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
};
const icon = (name) =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.server}</svg>`;
document.querySelectorAll("[data-icon]").forEach((node) => {
  node.innerHTML = icon(node.dataset.icon);
});

let token = "";
let data = null;
let page = "clients";
let query = "";
let filter = "all";
let clientPage = 1;
const pageSize = 50;
let timer;
let toastTimer;
let refreshing = false;
let dirty = false;
let session = 0;
let stateRequest = 0;
const modal = $("#modal");
const titles = {
  clients: [
    "FLEET OVERVIEW",
    "Your clients",
    "A live view of the machines that keep your work moving.",
    "Connect a client",
  ],
  keys: [
    "ACCESS MANAGEMENT",
    "Reporting keys",
    "Give your clients a secure way to report home.",
    "Create a key",
  ],
  views: [
    "SHARED VISIBILITY",
    "View groups",
    "Choose which machines belong together, and who can see them.",
    "Create a view group",
  ],
  settings: [
    "SERVER CONFIGURATION",
    "Server settings",
    "Set the defaults that keep your workspace running.",
    "",
  ],
};

function toast(message, error = false) {
  clearTimeout(toastTimer);
  const element = $("#toast");
  element.textContent = message;
  element.classList.toggle("error", error);
  element.hidden = false;
  toastTimer = setTimeout(() => {
    element.hidden = true;
  }, 4500);
}

function signOut(message = "") {
  session++;
  token = "";
  data = null;
  dirty = false;
  query = "";
  filter = "all";
  clientPage = 1;
  refreshing = false;
  clearTimeout(timer);
  closeModal();
  $("#console").hidden = true;
  $("#login").hidden = false;
  $("#page-content").replaceChildren();
  $("#admin-token").value = "";
  $("#login-error").hidden = !message;
  $("#login-error").textContent = message;
  $("#admin-token").focus();
}

async function api(path, body) {
  const requestSession = session;
  const response = await fetch(`/admin/api/${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    cache: "no-store",
    credentials: "omit",
    signal: AbortSignal.timeout(15000),
  });
  const result = await response.json().catch(() => ({}));
  if (session !== requestSession)
    throw new Error("This session has ended. Sign in to continue.");
  if (!response.ok) {
    if (response.status === 401 && data)
      signOut("Your session ended. Enter the admin token to reconnect.");
    const detail = Array.isArray(result.detail)
      ? result.detail
          .map(
            (item) => `${item.loc?.slice(1).join(".") || "Input"}: ${item.msg}`,
          )
          .join("; ")
      : result.detail;
    throw new Error(
      detail || `Request failed (${response.status}). Try again.`,
    );
  }
  return result;
}

function errorMessage(error) {
  return ["TimeoutError", "AbortError"].includes(error.name)
    ? "The server took too long to respond. Try again."
    : error instanceof TypeError
      ? "Cannot reach the server. Check your connection and try again."
      : error.message;
}

async function refresh(render = true, force = false) {
  if ((refreshing && !force) || !token) return;
  const currentRequest = ++stateRequest;
  refreshing = true;
  const currentSession = session;
  $("#refresh").disabled = true;
  try {
    const result = await api("state");
    if (session !== currentSession || currentRequest !== stateRequest) return;
    data = result;
    $("#connection-error").hidden = true;
    $("#connection-state").textContent = "Live connection";
    $(".live-indicator").classList.remove("disconnected");
    $("#sidebar-server").textContent = data.settings.server_name;
    $("#nav-count").textContent = data.clients.length;
    $("#last-sync").textContent =
      `Updated ${new Date(data.server_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })} · refreshes every ${data.settings.refresh_interval}s`;
    document.title = `${data.settings.server_name} · Administration`;
    if (
      render &&
      !dirty &&
      !modal.open &&
      !$("#client-search")?.matches(":focus")
    )
      renderPage();
  } catch (error) {
    if (session !== currentSession || currentRequest !== stateRequest) return;
    $("#connection-state").textContent = "Connection interrupted";
    $(".live-indicator").classList.add("disconnected");
    $("#connection-error").textContent =
      `${errorMessage(error)} The last received data is shown below.`;
    $("#connection-error").hidden = false;
    throw error;
  } finally {
    if (session === currentSession && currentRequest === stateRequest) {
      refreshing = false;
      $("#refresh").disabled = false;
      scheduleRefresh();
    }
  }
}

function scheduleRefresh() {
  clearTimeout(timer);
  if (token)
    timer = setTimeout(
      () => {
        if (document.hidden) scheduleRefresh();
        else refresh().catch(() => {});
      },
      (data?.settings.refresh_interval || 15) * 1000,
    );
}

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("button", event.currentTarget);
  button.disabled = true;
  button.textContent = "Connecting…";
  $("#login-error").hidden = true;
  token = $("#admin-token").value.trim();
  session++;
  try {
    data = await api("state");
    $("#admin-token").value = "";
    $("#login").hidden = true;
    $("#console").hidden = false;
    $("#sidebar-server").textContent = data.settings.server_name;
    $("#nav-count").textContent = data.clients.length;
    const initial = location.hash.slice(1);
    page = Object.hasOwn(titles, initial) ? initial : "clients";
    navigate(page);
    scheduleRefresh();
    $("#main").focus();
    refresh(false).catch(() => {});
  } catch (error) {
    token = "";
    $("#login-error").textContent = errorMessage(error);
    $("#login-error").hidden = false;
  } finally {
    button.disabled = false;
    button.innerHTML = 'Open console <span aria-hidden="true">→</span>';
  }
});
$("#signout").addEventListener("click", () => signOut());
$("#refresh").addEventListener("click", () =>
  refresh().catch((error) => toast(errorMessage(error), true)),
);
$("#navigation").addEventListener("click", (event) => {
  const button = event.target.closest("[data-page]");
  if (button) navigate(button.dataset.page);
});
window.addEventListener("hashchange", () => {
  if (data && Object.hasOwn(titles, location.hash.slice(1)))
    navigate(location.hash.slice(1));
});
window.addEventListener("beforeunload", (event) => {
  if (dirty) {
    event.preventDefault();
    event.returnValue = "";
  }
});

function navigate(next) {
  if (dirty && next === page) return;
  if (
    dirty &&
    next !== page &&
    !window.confirm("Discard unsaved server settings?")
  ) {
    history.replaceState(null, "", `#${page}`);
    return;
  }
  if (next !== page) dirty = false;
  page = next;
  history.replaceState(null, "", `#${page}`);
  document.querySelectorAll("[data-page]").forEach((button) => {
    button.classList.toggle("active", button.dataset.page === page);
    if (button.dataset.page === page)
      button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  const [eyebrow, title, description, action] = titles[page];
  $("#page-eyebrow").textContent = eyebrow;
  $("#page-title").textContent = title;
  $("#page-description").textContent = description;
  $("#breadcrumb").textContent = page === "clients" ? "Clients" : title;
  $("#primary-action").hidden = !action;
  $("#primary-action").innerHTML = `${icon("plus")}${e(action)}`;
  renderPage();
}
$("#primary-action").addEventListener("click", () =>
  ({ clients: connectClient, keys: createKey, views: () => editView(null) })[
    page
  ]?.(),
);

const clientName = (client) =>
  client.settings.display_name ||
  client.report?.name ||
  client.report?.hostname ||
  client.machine_id;
const badge = (status) =>
  `<span class="badge ${e(status)}">${e(status.charAt(0).toUpperCase() + status.slice(1))}</span>`;
const percent = (value) =>
  Number.isFinite(value) ? `${Math.round(value * 100)}%` : "—";
const metric = (value) =>
  `<div class="metric ${value > 0.85 ? "high" : ""}"><span class="metric-value">${percent(value)}</span>${Number.isFinite(value) ? `<progress max="1" value="${Math.min(1, Math.max(0, value))}" aria-label="${percent(value)} utilization"></progress>` : '<span class="muted">—</span>'}</div>`;
const age = (seconds) =>
  seconds === null
    ? "No report yet"
    : seconds < 60
      ? `${Math.floor(seconds)}s ago`
      : seconds < 3600
        ? `${Math.floor(seconds / 60)}m ago`
        : seconds < 86400
          ? `${Math.floor(seconds / 3600)}h ago`
          : `${Math.floor(seconds / 86400)}d ago`;
const time = (value) =>
  value
    ? new Date(value).toLocaleString([], {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "Not received";
const duration = (seconds) =>
  !Number.isFinite(seconds)
    ? "—"
    : seconds >= 86400
      ? `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h`
      : seconds >= 3600
        ? `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
        : `${Math.floor(seconds / 60)}m`;
const maskedKey = (key) =>
  `${key.slice(0, 5)}${"•".repeat(12)}${key.slice(-4)}`;
const actionButton = (action, id, label, symbol, extra = "") =>
  `<button type="button" class="button ghost small" data-action="${action}" data-id="${e(id)}" aria-label="${e(label)}" title="${e(label)}" ${extra}>${icon(symbol)}</button>`;
const empty = (symbol, title, text, action, button) =>
  `<div class="empty-state"><div class="empty-symbol">${icon(symbol)}</div><h3>${e(title)}</h3><p>${e(text)}</p>${action ? `<button type="button" class="button primary" data-action="${action}">${icon("plus")}${e(button)}</button>` : ""}</div>`;

function renderPage() {
  if (!data) return;
  $("#page-content").innerHTML = {
    clients: clientsPage,
    keys: keysPage,
    views: viewsPage,
    settings: settingsPage,
  }[page]();
  if (page === "clients") {
    $("#client-search").value = query;
    $("#client-search").addEventListener("input", (event) => {
      query = event.target.value;
      clientPage = 1;
      renderClientsTable();
    });
    renderClientsTable();
  }
  if (page === "settings") {
    $("#settings-form").addEventListener("input", () => {
      dirty = true;
    });
    $("#settings-form").addEventListener("submit", saveSettings);
  }
}

function clientsPage() {
  const total = data.clients.length;
  const online = data.clients.filter(
    (client) => client.status === "online",
  ).length;
  const offline = data.clients.filter((client) =>
    ["offline", "waiting"].includes(client.status),
  ).length;
  const blocked = data.clients.filter(
    (client) => client.status === "blocked",
  ).length;
  const stats = [
    ["Registered clients", total, "Across your workspace", ""],
    [
      "Online now",
      online,
      `Reported in the last ${duration(data.settings.offline_after_seconds)}`,
      "online",
    ],
    ["Offline / waiting", offline, "Awaiting a fresh report", "offline"],
    ["Blocked", blocked, "Incoming reports disabled", "blocked"],
  ];
  return `<div class="fleet-summary">${stats.map(([label, value, detail, status]) => `<div class="summary-cell"><span class="summary-label">${status ? `<i class="signal-dot ${status}"></i>` : ""}${label}</span><div class="summary-value ${status === "online" ? "teal" : ""}">${value.toLocaleString()}</div><span class="summary-detail">${e(detail)}</span></div>`).join("")}</div>${
    total
      ? `<div class="fleet-signal"><span class="fleet-signal-label">FLEET SIGNAL</span><div class="signal-bars">${data.clients
          .slice(0, 100)
          .map(
            (client) =>
              `<button type="button" class="signal-segment ${client.status}" data-action="client" data-id="${e(client.machine_id)}" title="${e(clientName(client))} · ${client.status}" aria-label="${e(clientName(client))}, ${client.status}"></button>`,
          )
          .join(
            "",
          )}</div><span class="signal-caption">One signal per client${total > 100 ? " · first 100 shown" : ""}</span></div>`
      : ""
  }<div class="panel"><div class="toolbar"><div class="search-wrap">${icon("search")}<input id="client-search" type="search" aria-label="Search clients" placeholder="Search by name, host, or machine ID"></div><div class="filters" aria-label="Filter clients">${["all", "online", "offline", "blocked"].map((status) => `<button type="button" class="filter ${filter === status ? "active" : ""}" data-action="filter" data-id="${status}" aria-pressed="${filter === status}">${status === "all" ? "All clients" : status.charAt(0).toUpperCase() + status.slice(1)}</button>`).join("")}</div></div><div id="clients-table"></div></div>`;
}

function renderClientsTable() {
  const search = query.toLowerCase();
  const clients = data.clients.filter(
    (client) =>
      (filter === "all" ||
        client.status === filter ||
        (filter === "offline" && client.status === "waiting")) &&
      [
        clientName(client),
        client.machine_id,
        client.report?.hostname,
        client.report?.local_ip,
      ].some((value) =>
        String(value || "")
          .toLowerCase()
          .includes(search),
      ),
  );
  if (!clients.length) {
    $("#clients-table").innerHTML = data.clients.length
      ? empty(
          "search",
          "No matching clients",
          "Try another name or choose a different status filter.",
        )
      : empty(
          "servers",
          "Your fleet starts here",
          "Connect your first client to see its health, resource usage, and reporting status.",
          "connect",
          "Connect a client",
        );
    return;
  }
  clientPage = Math.min(
    clientPage,
    Math.max(1, Math.ceil(clients.length / pageSize)),
  );
  const start = (clientPage - 1) * pageSize;
  const visibleClients = clients.slice(start, start + pageSize);
  $("#clients-table").innerHTML =
    `<div class="table-scroll"><table><thead><tr><th>Client</th><th>Status</th><th>CPU</th><th>Memory</th><th>GPUs</th><th>Last report</th><th><span class="muted">Details</span></th></tr></thead><tbody>${visibleClients.map((client) => `<tr><td><div class="client-cell"><span class="machine-icon">${icon("server")}</span><div><button type="button" class="client-name" data-action="client" data-id="${e(client.machine_id)}">${e(clientName(client))}</button><div class="client-subtitle">${e(client.report?.local_ip || client.report?.hostname || client.machine_id)}</div></div></div></td><td>${badge(client.status)}</td><td>${metric(client.report?.cpu_usage)}</td><td>${metric(client.report?.ram_usage)}</td><td><span class="mono">${client.report ? client.report.gpu_status?.length || "—" : "—"}</span></td><td class="muted"><span title="${e(time(client.report?.created_at))}">${age(client.age_seconds)}</span></td><td><div class="row-actions">${actionButton("client", client.machine_id, `Manage ${clientName(client)}`, "arrow")}</div></td></tr>`).join("")}</tbody></table></div><div class="table-caption"><span>${start + 1}–${Math.min(start + pageSize, clients.length)} of ${clients.length} matching clients</span>${clients.length > pageSize ? `<span class="pagination"><button type="button" class="button ghost small" data-action="previous-clients" ${clientPage === 1 ? "disabled" : ""}>Previous</button><span>${clientPage} / ${Math.ceil(clients.length / pageSize)}</span><button type="button" class="button ghost small" data-action="next-clients" ${start + pageSize >= clients.length ? "disabled" : ""}>Next</button></span>` : ""}<span>Online within ${data.settings.offline_after_seconds}s of last report</span></div>`;
}

function keysPage() {
  if (!data.report_keys.length)
    return `<div class="panel">${empty("key", "Give your first client access", "A reporting key lets a client send telemetry to this server. Create one to get started.", "create-key", "Create a key")}</div>`;
  return `<p class="section-note">Reporting keys allow incoming reports. Keep them private and revoke any key you no longer trust.</p><div class="panel"><div class="panel-heading"><div><h3>Reporting access</h3><p>${data.report_keys.length} active ${data.report_keys.length === 1 ? "key" : "keys"}</p></div>${badge("enabled")}</div><div class="table-scroll"><table><thead><tr><th>Key name</th><th>Reporting key</th><th>Clients</th><th>Owner</th><th>Actions</th></tr></thead><tbody>${data.report_keys.map((key) => `<tr><td><div class="key-description">${e(key.report_key_desc || "Untitled key")}</div><div class="key-note">Client reporting access</div></td><td><div class="key-value"><code>${e(maskedKey(key.report_key))}</code>${actionButton("reveal-key", key.report_key, "Reveal reporting key", "eye")}${actionButton("copy", key.report_key, "Copy reporting key", "copy")}</div></td><td class="mono">${key.machines.length}</td><td class="muted">${e(key.user_id)}</td><td><div class="row-actions">${actionButton("connect-key", key.report_key, "Download client configuration", "download")}${actionButton("edit-key", key.report_key, "Edit key name", "edit")}${actionButton("delete-key", key.report_key, "Revoke reporting key", "trash")}</div></td></tr>`).join("")}</tbody></table></div></div>`;
}

function viewsPage() {
  if (!data.view_groups.length)
    return `<div class="panel">${empty("layers", "Share a focused view", "Create a view group to share a selection of clients through a dedicated read-only key.", "create-view", "Create a view group")}</div>`;
  return `<p class="section-note">Each view key grants read-only access to its selected clients. Disable a view to stop access immediately.</p><div class="cards-grid">${data.view_groups
    .map((group) => {
      const status = !group.view_enabled
        ? "disabled"
        : group.view_timer && new Date(group.view_timer) <= new Date()
          ? "expired"
          : "enabled";
      return `<article class="view-card"><div class="view-card-top"><span class="view-card-icon">${icon("layers")}</span>${badge(status)}</div><h3>${e(group.view_name || "Untitled view")}</h3><p class="view-description">${e(group.view_desc || "A shared view of your selected clients.")}</p><div class="key-value"><code>${e(maskedKey(group.view_key))}</code>${actionButton("reveal-view", group.view_key, "Reveal view key", "eye")}${actionButton("copy", group.view_key, "Copy view key", "copy")}</div><div class="client-chips">${group.view_machines
        .slice(0, 4)
        .map(
          (id) =>
            `<span class="chip">${e(data.clients.find((client) => client.machine_id === id) ? clientName(data.clients.find((client) => client.machine_id === id)) : id)}</span>`,
        )
        .join(
          "",
        )}${group.view_machines.length > 4 ? `<span class="chip">+${group.view_machines.length - 4} more</span>` : ""}${!group.view_machines.length ? '<span class="muted">No clients selected</span>' : ""}</div><div class="view-meta">${group.view_timer ? `Expires ${e(time(group.view_timer))}` : "No expiration"}</div><div class="view-card-bottom"><button type="button" class="button secondary small" data-action="edit-view" data-id="${e(group.view_key)}">${icon("edit")}Edit view</button>${actionButton("delete-view", group.view_key, "Delete view group", "trash")}</div></article>`;
    })
    .join("")}</div>`;
}

function settingsPage() {
  const s = data.settings;
  return `<div class="settings-layout"><form id="settings-form"><section class="panel"><div class="panel-heading"><div><h3>Workspace preferences</h3><p>Make this server yours.</p></div></div><div class="form-body"><div class="field"><label for="server-name">Server name</label><input id="server-name" name="server_name" value="${e(s.server_name)}" required maxlength="80"></div><div class="field-row"><div class="field"><label for="refresh-interval">Console refresh (seconds)</label><input id="refresh-interval" name="refresh_interval" type="number" min="5" max="300" value="${s.refresh_interval}" required><p class="field-help">How often this panel fetches fresh data.</p></div><div class="field"><label for="offline-after">Offline threshold (seconds)</label><input id="offline-after" name="offline_after_seconds" type="number" min="10" max="86400" value="${s.offline_after_seconds}" required><p class="field-help">Mark a client offline after this silence.</p></div></div></div></section><section class="panel"><div class="panel-heading"><div><h3>Client reporting</h3><p>Control enrollment and default configuration.</p></div></div><div class="form-body"><div class="field-row"><div class="field"><label for="default-interval">Default reporting interval (seconds)</label><input id="default-interval" name="default_report_interval" type="number" min="1" max="86400" value="${s.default_report_interval}" required><p class="field-help">Used in newly downloaded client configs.</p></div><div class="field"><label for="capacity">Client capacity</label><input id="capacity" name="max_machines" type="number" min="${Math.max(1, data.clients.length)}" max="10000" value="${s.max_machines}" required><p class="field-help">${data.clients.length.toLocaleString()} registered · up to 10,000 supported.</p></div></div><div class="toggle-row"><div><label for="enrollment">Accept new clients</label><p>Existing clients can continue reporting when disabled.</p></div><input id="enrollment" name="accept_new_clients" type="checkbox" ${s.accept_new_clients ? "checked" : ""}></div><p id="settings-error" class="form-error" role="alert" hidden></p></div><div class="form-actions"><span class="field-help">Changes apply immediately.</span><button type="submit" class="button primary">Save changes</button></div></section></form><aside class="settings-aside"><section class="panel"><div class="panel-heading"><h3>Server at a glance</h3></div><div class="form-body">${[
    ["Version", data.runtime.version],
    ["Uptime", duration(data.runtime.uptime_seconds)],
    ["Python", data.runtime.python],
    [
      "Storage",
      data.runtime.persistent ? "Persistent · SQLite" : "Temporary · memory",
    ],
    ["Administrator", data.user_id],
  ]
    .map(
      ([label, value]) =>
        `<div class="deployment-row"><span>${e(label)}</span><strong>${e(value)}</strong></div>`,
    )
    .join(
      "",
    )}<p class="deployment-note">${data.runtime.persistent ? "Keys, views, and client settings are saved across restarts. Live telemetry resumes when clients report again." : "This instance is running without persistent storage. Changes will be lost when the server restarts."}</p></div></section><section class="panel settings-description"><h3>Deployment & security</h3><p>The admin token stays on the server and is never shown here. Change <code>MXSTATUS_ADMIN_TOKEN</code> in your deployment to rotate it.</p><p class="deployment-note">Allowed browser origins: ${e(data.runtime.cors_origins.join(", ") || "same origin only")}.</p><p class="deployment-note">Environment settings require a server restart. Run one server worker with the current storage model.</p></section></aside></div>`;
}

async function saveSettings(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const values = new FormData(form);
  const body = {
    server_name: values.get("server_name").trim(),
    accept_new_clients: values.has("accept_new_clients"),
  };
  for (const key of [
    "refresh_interval",
    "offline_after_seconds",
    "default_report_interval",
    "max_machines",
  ])
    body[key] = Number(values.get(key));
  const button = $("button[type=submit]", form);
  button.disabled = true;
  $("#settings-error").hidden = true;
  try {
    await api("settings", body);
    dirty = false;
    await refresh(false, true);
    renderPage();
    toast("Server settings saved");
  } catch (error) {
    if (data && $("#settings-error")) {
      $("#settings-error").textContent = errorMessage(error);
      $("#settings-error").hidden = false;
    }
  } finally {
    button.disabled = false;
  }
}

function openModal(title, content, wide = false, eyebrow = "WORKSPACE") {
  $("#modal-title").textContent = title;
  $("#modal-eyebrow").textContent = eyebrow;
  $("#modal-content").innerHTML = content;
  modal.classList.toggle("wide", wide);
  if (!modal.open) modal.showModal();
}
function closeModal() {
  if (modal.open) modal.close();
  $("#modal-content").replaceChildren();
}
$("#modal-close").addEventListener("click", closeModal);
modal.addEventListener("cancel", (event) => {
  event.preventDefault();
  closeModal();
});
const formError = '<p class="form-error" role="alert" hidden></p>';
const modalActions = (label) =>
  `<div class="modal-actions"><button type="button" class="button secondary" data-action="close">Cancel</button><button type="submit" class="button primary">${e(label)}</button></div>`;

function handleForm(callback) {
  const form = $("form", modal);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = $("button[type=submit]", form);
    const errorElement = $(".form-error", form);
    button.disabled = true;
    errorElement.hidden = true;
    try {
      await callback(new FormData(form));
    } catch (error) {
      if (form.isConnected) {
        errorElement.textContent = errorMessage(error);
        errorElement.hidden = false;
      } else toast(errorMessage(error), true);
    } finally {
      button.disabled = false;
    }
  });
}
async function mutation(path, body, message) {
  const mutationSession = session;
  const result = await api(path, body);
  closeModal();
  await refresh(false, true).catch(() => {});
  if (session !== mutationSession)
    throw new Error("This session has ended. Sign in to continue.");
  if (data && !dirty) renderPage();
  toast(message);
  return result;
}

function createKey() {
  openModal(
    "Create a reporting key",
    `<form><div class="modal-body"><p>Use a descriptive name to recognize where this key is installed. A secure key will be generated for you.</p><div class="field"><label for="key-name">Key name</label><input id="key-name" name="description" placeholder="e.g. Research workstations" maxlength="200" required></div>${ownerSelect()}${formError}</div>${modalActions("Create key")}</form>`,
    false,
    "REPORTING ACCESS",
  );
  handleForm(async (values) => {
    const result = await mutation(
      "keys",
      {
        report_key_desc: values.get("description"),
        user_id: values.get("owner") || data.user_id,
      },
      "Reporting key created",
    );
    showSecret(result.report_key, "Reporting key created", true);
  });
}
function ownerSelect(selected = data.user_id, disabled = false) {
  return data.users.length > 1
    ? `<div class="field"><label for="owner">Owner</label><select id="owner" name="owner" ${disabled ? "disabled" : ""}>${data.users.map((user) => `<option value="${e(user)}" ${user === selected ? "selected" : ""}>${e(user)}</option>`).join("")}</select></div>`
    : "";
}
function editKey(key) {
  openModal(
    "Edit key name",
    `<form><div class="modal-body"><div class="field"><label for="key-description">Key name</label><input id="key-description" name="description" maxlength="200" value="${e(key.report_key_desc)}" required></div>${formError}</div>${modalActions("Save name")}</form>`,
  );
  handleForm((values) =>
    mutation(
      "keys/update",
      {
        report_key: key.report_key,
        report_key_desc: values.get("description"),
      },
      "Key name saved",
    ),
  );
}
function showSecret(key, title, reporting = false) {
  openModal(
    title,
    `<div class="modal-body"><p>${reporting ? "This key lets clients send reports to the server. Keep it private." : "Anyone with this key can read reports in this view group. Share it only with intended viewers."}</p><div class="secret-box">${e(key)}</div></div><div class="modal-actions"><button type="button" class="button secondary" data-action="copy" data-id="${e(key)}">${icon("copy")}Copy key</button>${reporting ? `<button type="button" class="button primary" data-action="connect-key" data-id="${e(key)}">Connect a client</button>` : '<button type="button" class="button primary" data-action="close">Done</button>'}</div>`,
  );
}

function connectClient(selected = "") {
  if (!data.report_keys.length) {
    createKey();
    return;
  }
  openModal(
    "Connect a client",
    `<form><div class="modal-body"><p>Download a configuration for a new Linux client, then start the reporting service on that machine.</p><ol class="connect-steps"><li><span>Install MXStatus and its Python dependencies on the client.</span></li><li><span>Save the downloaded file as <strong>client/config.json</strong> in your checkout. Keep it private.</span></li><li><span>From the checkout, run <code>./client/installer install</code> with your virtual environment active.</span></li></ol>${!data.settings.accept_new_clients ? '<div class="banner warning">New client enrollment is disabled. Enable it in Server settings before connecting a new machine.</div>' : ""}<div class="field"><label for="connect-key">Reporting key</label><select id="connect-key" name="key">${data.report_keys.map((key) => `<option value="${e(key.report_key)}" ${key.report_key === selected ? "selected" : ""}>${e(key.report_key_desc || "Untitled key")} · ${e(key.report_key.slice(-4))}</option>`).join("")}</select></div><div class="field"><label for="client-label">Client name <span class="muted">(optional)</span></label><input id="client-label" name="name" maxlength="120" placeholder="Use the machine’s hostname"></div><div class="field"><label for="server-url">Server address</label><input id="server-url" name="server" type="url" required value="${e(location.origin)}"><p class="field-help">Use an HTTPS address reachable from the client.</p></div><div class="field"><label for="client-interval">Reporting interval (seconds)</label><input id="client-interval" name="interval" type="number" min="1" max="86400" value="${data.settings.default_report_interval}" required></div>${formError}</div>${modalActions("Download config.json")}</form>`,
    false,
    "CLIENT SETUP",
  );
  handleForm(async (values) => {
    const url = new URL(values.get("server"));
    if (
      !["http:", "https:"].includes(url.protocol) ||
      url.username ||
      url.password ||
      url.search ||
      url.hash
    )
      throw new Error(
        "Enter an HTTP(S) server URL without credentials, query, or fragment.",
      );
    const config = {
      server_address: url.href.replace(/\/$/, ""),
      report_key: values.get("key"),
      report_interval: Number(values.get("interval")),
      logger_level: "info",
      display_name: values.get("name"),
      display_note: "",
      display_warning: "",
    };
    const download = URL.createObjectURL(
      new Blob([JSON.stringify(config, null, 2) + "\n"], {
        type: "application/json",
      }),
    );
    const link = document.createElement("a");
    link.href = download;
    link.download = "config.json";
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(download), 1000);
    toast("Client configuration downloaded");
  });
}

function editClient(client) {
  const report = client.report;
  openModal(
    clientName(client),
    `<form><div class="modal-body"><div class="detail-caption">${e(client.machine_id)}</div><div class="detail-strip"><div><label>Status</label>${badge(client.status)}</div><div><label>CPU</label><strong>${percent(report?.cpu_usage)}</strong></div><div><label>Memory</label><strong>${percent(report?.ram_usage)}</strong></div><div><label>Uptime</label><strong>${duration(report?.uptime)}</strong></div><div><label>Last report</label><strong>${age(client.age_seconds)}</strong></div></div><div class="field-row"><div class="field"><label for="client-name">Display name</label><input id="client-name" name="name" maxlength="120" value="${e(client.settings.display_name)}" placeholder="${e(report?.hostname || "Use reported name")}"></div><div class="field"><label for="report-interval">Reporting interval (seconds)</label><input id="report-interval" name="interval" type="number" min="1" max="86400" value="${client.settings.report_interval ?? ""}" placeholder="Use the client’s local setting"><p class="field-help">Updated after the next successful report.</p></div></div><div class="field"><label for="client-notes">Notes</label><textarea id="client-notes" name="notes" rows="2" maxlength="2000" placeholder="Location, purpose, or maintenance notes">${e(client.settings.notes)}</textarea></div><div class="field toggle-row"><div><label for="client-enabled">Allow incoming reports</label><p>Turn off to block reports from this machine.</p></div><input type="checkbox" id="client-enabled" name="enabled" ${client.settings.enabled ? "checked" : ""}></div>${report ? clientTelemetry(report) : '<div class="banner">Waiting for the first report. Saved settings will apply when this client connects.</div>'}${formError}</div><div class="modal-actions"><button type="button" class="button danger small" data-action="delete-client" data-id="${e(client.machine_id)}">Forget client</button><button type="button" class="button secondary" data-action="close">Cancel</button><button type="submit" class="button primary">Save client</button></div></form>`,
    true,
    "CLIENT DETAILS",
  );
  handleForm((values) =>
    mutation(
      "clients/update",
      {
        machine_id: client.machine_id,
        display_name: values.get("name").trim(),
        notes: values.get("notes"),
        enabled: values.has("enabled"),
        report_interval: values.get("interval")
          ? Number(values.get("interval"))
          : null,
      },
      "Client settings saved",
    ),
  );
}
function clientTelemetry(report) {
  return `<div class="detail-facts">${[
    ["Hostname", report.hostname],
    ["Operating system", report.linux_distro || report.platform],
    ["CPU", report.cpu_model || report.processor],
    [
      "Local / public IP",
      [report.local_ip, report.public_ip].filter(Boolean).join(" / "),
    ],
    [
      "Memory",
      report.ram_total ? `${(report.ram_total / 1024).toFixed(1)} GiB` : null,
    ],
    ["Received", time(report.created_at)],
  ]
    .map(
      ([label, value]) =>
        `<div><label>${label}</label><span>${e(value || "—")}</span></div>`,
    )
    .join(
      "",
    )}</div>${report.gpu_status?.length ? `<section class="detail-section"><h3>Graphics processors</h3><div class="table-scroll detail-table"><table><thead><tr><th>GPU</th><th>Utilization</th><th>Memory</th><th>Temperature</th></tr></thead><tbody>${report.gpu_status.map((gpu) => `<tr><td>${e(gpu.gpu_name || `GPU ${gpu.index}`)}</td><td>${percent(gpu.gpu_usage)}</td><td>${percent(gpu.memory_usage)}</td><td>${gpu.temperature ?? "—"} ${gpu.temperature !== null ? "°C" : ""}</td></tr>`).join("")}</tbody></table></div></section>` : ""}${report.disk_info?.length ? `<section class="detail-section"><h3>Storage</h3><div class="table-scroll detail-table"><table><thead><tr><th>Mount</th><th>Capacity</th><th>Available</th><th>Used</th></tr></thead><tbody>${report.disk_info.map((disk) => `<tr><td class="mono">${e(disk.mounted_on || disk.filesystem || "—")}</td><td>${Number.isFinite(disk.size) ? `${disk.size.toFixed(1)} GiB` : "—"}</td><td>${Number.isFinite(disk.avail) ? `${disk.avail.toFixed(1)} GiB` : "—"}</td><td>${percent(disk.usage)}</td></tr>`).join("")}</tbody></table></div></section>` : ""}${report.gpu_compute_processes?.length ? `<section class="detail-section"><h3>GPU processes</h3><div class="table-scroll detail-table"><table><thead><tr><th>Process</th><th>PID</th><th>GPU</th><th>GPU memory</th></tr></thead><tbody>${report.gpu_compute_processes.map((proc) => `<tr><td>${e(proc.command || "—")}</td><td>${e(proc.pid ?? "—")}</td><td>${e(proc.gpu_index ?? "—")}</td><td>${Number.isFinite(proc.gpu_mem_used) ? `${proc.gpu_mem_used.toFixed(0)} MiB` : "—"}</td></tr>`).join("")}</tbody></table></div></section>` : ""}`;
}

function clientChecklist(owner, selected = []) {
  const clients = data.clients.filter((client) => client.user_id === owner);
  return clients.length
    ? clients
        .map(
          (client) =>
            `<label><input type="checkbox" name="machines" value="${e(client.machine_id)}" ${selected.includes(client.machine_id) ? "checked" : ""}><span>${e(clientName(client))}</span><small>${e(client.status)}</small></label>`,
        )
        .join("")
    : '<p class="muted">No registered clients for this owner yet. You can add clients to this group later.</p>';
}
function localDate(value) {
  if (!value) return "";
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}
function editView(group) {
  const owner = group?.user_id || data.user_id;
  openModal(
    group ? "Edit view group" : "Create a view group",
    `<form><div class="modal-body"><div class="field"><label for="view-name">View name</label><input id="view-name" name="name" maxlength="120" value="${e(group?.view_name || "")}" placeholder="e.g. Research lab" required></div><div class="field"><label for="view-description">Description</label><input id="view-description" name="description" maxlength="500" value="${e(group?.view_desc || "")}" placeholder="What does this group cover?"></div>${ownerSelect(owner, !!group)}<div class="field"><label>Included clients</label><div class="checklist" id="client-checklist">${clientChecklist(owner, group?.view_machines)}</div></div><div class="field"><label for="view-expiry">Access expires <span class="muted">(optional, local time)</span></label><input id="view-expiry" name="expires" type="datetime-local" value="${e(localDate(group?.view_timer))}"><p class="field-help">Leave empty for access without an expiration.</p></div><div class="field toggle-row"><div><label for="view-enabled">Enable this view</label><p>Allow viewers with the key to read these reports.</p></div><input type="checkbox" id="view-enabled" name="enabled" ${!group || group.view_enabled ? "checked" : ""}></div>${formError}</div>${modalActions(group ? "Save view group" : "Create view group")}</form>`,
    false,
    "SHARED VISIBILITY",
  );
  $("#owner", modal)?.addEventListener("change", (event) => {
    $("#client-checklist").innerHTML = clientChecklist(event.target.value);
  });
  handleForm(async (values) => {
    const body = {
      view_name: values.get("name").trim(),
      view_desc: values.get("description"),
      view_machines: values.getAll("machines"),
      view_enabled: values.has("enabled"),
      view_timer: values.get("expires")
        ? new Date(values.get("expires")).toISOString()
        : null,
    };
    if (group) body.view_key = group.view_key;
    const result = await mutation(
      group
        ? "views/update"
        : `views?user_id=${encodeURIComponent(values.get("owner") || owner)}`,
      body,
      group ? "View group saved" : "View group created",
    );
    if (!group) showSecret(result.view_key, "View group created");
  });
}

function confirmAction(title, description, label, callback) {
  openModal(
    title,
    `<form><div class="modal-body"><p>${e(description)}</p>${formError}</div><div class="modal-actions"><button type="button" class="button secondary" data-action="close">Cancel</button><button type="submit" class="button danger">${e(label)}</button></div></form>`,
    false,
    "CONFIRM CHANGE",
  );
  handleForm(callback);
}

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button || !data) return;
  const id = button.dataset.id;
  try {
    switch (button.dataset.action) {
      case "close":
        closeModal();
        break;
      case "connect":
        connectClient();
        break;
      case "connect-key":
        connectClient(id);
        break;
      case "create-key":
        createKey();
        break;
      case "create-view":
        editView(null);
        break;
      case "client": {
        const client = data.clients.find((item) => item.machine_id === id);
        if (client) editClient(client);
        break;
      }
      case "previous-clients":
        clientPage = Math.max(1, clientPage - 1);
        renderClientsTable();
        break;
      case "next-clients":
        clientPage++;
        renderClientsTable();
        break;
      case "filter":
        filter = id;
        clientPage = 1;
        document.querySelectorAll(".filter").forEach((item) => {
          item.classList.toggle("active", item.dataset.id === filter);
          item.setAttribute("aria-pressed", item.dataset.id === filter);
        });
        renderClientsTable();
        break;
      case "copy":
        if (!navigator.clipboard)
          throw new Error(
            "Clipboard access is unavailable. Reveal the key and copy it manually.",
          );
        await navigator.clipboard.writeText(id);
        toast("Copied to clipboard");
        break;
      case "reveal-key":
        showSecret(id, "Reporting key", true);
        break;
      case "reveal-view":
        showSecret(id, "View key");
        break;
      case "edit-key":
        editKey(data.report_keys.find((key) => key.report_key === id));
        break;
      case "edit-view":
        editView(data.view_groups.find((group) => group.view_key === id));
        break;
      case "delete-key": {
        const key = data.report_keys.find((item) => item.report_key === id);
        confirmAction(
          "Revoke this reporting key?",
          `Clients using “${key.report_key_desc || "Untitled key"}” will no longer be able to report with it. Clients without another reporting key will be removed from the fleet and all views.`,
          "Revoke key",
          () =>
            mutation(
              "keys/delete",
              { report_key: id },
              "Reporting key revoked",
            ),
        );
        break;
      }
      case "delete-view":
        confirmAction(
          "Delete this view group?",
          "Its view key will stop working immediately. Your clients and reporting keys will remain available.",
          "Delete view group",
          () =>
            mutation("views/delete", { view_key: id }, "View group deleted"),
        );
        break;
      case "delete-client":
        confirmAction(
          "Forget this client?",
          "This removes its saved settings, last report, and view memberships. If enrollment is enabled, a running client can register again. Block incoming reports instead to keep it out.",
          "Forget client",
          () =>
            mutation("clients/delete", { machine_id: id }, "Client forgotten"),
        );
        break;
    }
  } catch (error) {
    toast(errorMessage(error), true);
  }
});
