"use strict";
let S = null;
const $ = (id) => document.getElementById(id);
const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const tag = (v) => `<span class="tag ${esc(v)}">${esc(v)}</span>`;
const cap = (v) => v.charAt(0) + v.slice(1).toLowerCase();

function toast(text, err) {
  const m = $("msg");
  m.textContent = text; m.className = err ? "err" : ""; m.style.display = "block";
  clearTimeout(toast.t); toast.t = setTimeout(() => (m.style.display = "none"), 4000);
}

async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Request failed");
  return data;
}

function table(id, cols, rows, emptyText) {
  const el = $(id);
  if (!rows.length) { el.innerHTML = `<tr><td class="empty">${esc(emptyText)}</td></tr>`; return; }
  el.innerHTML = `<thead><tr>${cols.map((c) => `<th>${esc(c[0])}</th>`).join("")}</tr></thead><tbody>` +
    rows.map((r) => `<tr>${cols.map((c) => `<td>${c[1](r)}</td>`).join("")}</tr>`).join("") + "</tbody>";
}

function render() {
  const m = S.summary;
  $("kpis").innerHTML = [["Open requests", m.unfulfilled, `of ${m.total_requests} total`], ["Fulfilled", m.fulfilled, "requests complete"],
    ["Units delivered", m.units_delivered.toLocaleString(), `of ${m.units_requested.toLocaleString()} requested`],
    ["Fulfillment rate", m.fulfillment_rate + "%", "units delivered / requested"]]
    .map((k) => `<div class="kpi"><small>${k[0]}</small><b>${k[1]}</b><small>${k[2]}</small></div>`).join("");

  const order = S.queue, byId = Object.fromEntries(S.requests.map((r) => [r.request_id, r]));
  table("t-queue", [["#", (r) => order.indexOf(r.request_id) + 1], ["Request", (r) => esc(r.request_id)], ["Shelter", (r) => esc(r.shelter)],
    ["Item", (r) => esc(r.item)], ["Urgency", (r) => tag(r.urgency)], ["Outstanding", (r) => r.outstanding.toLocaleString()]],
    order.map((id) => byId[id]), "No open requests. Submit one to get started.");
  const reqCols = [["Request", (r) => esc(r.request_id)], ["Shelter", (r) => esc(r.shelter)], ["Item", (r) => esc(r.item)],
    ["Urgency", (r) => tag(r.urgency)], ["Requested", (r) => r.requested.toLocaleString()], ["Fulfilled", (r) => r.fulfilled.toLocaleString()], ["Status", (r) => tag(r.status)]];
  table("t-requests", reqCols, S.requests, "No requests yet.");
  table("t-unfulfilled", reqCols, S.requests.filter((r) => r.status !== "FULFILLED"), "Every request is fulfilled.");
  table("t-inventory", [["Item", (r) => esc(r.item)], ["Quantity", (r) => r.quantity.toLocaleString()], ["Warehouse ID", (r) => esc(r.warehouse_id)]], S.inventory, "No inventory recorded.");
  table("t-shelters", [["ID", (r) => esc(r.shelter_id)], ["Name", (r) => esc(r.name)], ["Priority", (r) => r.priority], ["Location", (r) => `(${r.x}, ${r.y})`]], S.shelters, "No shelters registered.");
  table("t-log", [["Time", (r) => esc(r.time)], ["Request", (r) => esc(r.request_id)], ["Shelter", (r) => esc(r.shelter)], ["Item", (r) => esc(r.item)],
    ["Qty", (r) => r.quantity.toLocaleString()], ["From", (r) => esc(r.warehouse_id)], ["Distance", (r) => r.distance], ["Result", (r) => tag(r.result)]],
    S.logs, "No allocations yet. Run allocation to match stock to requests.");

  const opts = (list, key, label) => list.map((x) => `<option value="${esc(x[key])}">${esc(x[label])} (${esc(x[key])})</option>`).join("");
  $("sel-shelter").innerHTML = opts(S.shelters, "shelter_id", "name");
  $("sel-wh").innerHTML = opts(S.warehouses, "warehouse_id", "name");
  $("items").innerHTML = [...new Set(S.inventory.map((r) => r.item))].map((i) => `<option value="${esc(i)}">`).join("");
}

async function refresh() { S = await api("/api/state"); render(); }

async function run(fn, okText) {
  try { await fn(); await refresh(); if (okText) toast(okText); } catch (e) { toast(e.message, true); }
}

function bindForm(id, path, okText) {
  $(id).addEventListener("submit", (e) => {
    e.preventDefault();
    const form = e.target, data = Object.fromEntries(new FormData(form));
    run(async () => { await api(path, data); form.reset(); }, okText);
  });
}

document.querySelectorAll("#tabs button").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll("#tabs button").forEach((x) => x.classList.toggle("on", x === b));
  document.querySelectorAll(".tab").forEach((t) => (t.hidden = t.id !== "tab-" + b.dataset.tab));
}));
$("btn-allocate").addEventListener("click", () => run(async () => {
  const r = await api("/api/allocate", {});
  toast(r.allocations ? `${r.allocations} allocation(s) made` : "Nothing to allocate: no open requests or no matching stock", !r.allocations);
}));
$("btn-reset").addEventListener("click", () => run(() => api("/api/reset", {}), "Sample data restored"));
bindForm("f-request", "/api/requests", "Request submitted");
bindForm("f-stock", "/api/stock", "Inventory updated");
bindForm("f-shelter", "/api/shelters", "Shelter registered");
refresh().catch((e) => toast(e.message, true));
