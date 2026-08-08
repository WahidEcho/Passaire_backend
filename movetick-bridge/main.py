import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv

from routers import guests, whatsapp, scanner, events, state, email, whatsapp_cloud
from services.greenapi import set_webhook

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

app = FastAPI(
    title="Passaire Backend",
    description="Event management & WhatsApp ticketing API — Powered by Green API + Supabase",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(events.router)
app.include_router(guests.router)
app.include_router(whatsapp.router)
app.include_router(scanner.router)
app.include_router(state.router)
app.include_router(email.router)
app.include_router(whatsapp_cloud.router)


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {"status": "Passaire backend is running 🎟️"}


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── One-time webhook registration ──────────────────────────────────────────────
@app.post("/setup-webhook")
async def setup_webhook(request: Request):
    """
    Call this ONCE after deploying to Railway to register the
    Green API webhook URL automatically. Visit /admin and click
    'Register Webhook', or POST /setup-webhook directly.
    """
    base_url    = str(request.base_url).rstrip("/")
    webhook_url = f"{base_url}/whatsapp/webhook"
    result      = set_webhook(webhook_url)
    return {"registered": webhook_url, "green_api_response": result}


# ── Admin Panel (single-page HTML + JS) ───────────────────────────────────────
@app.get("/admin", response_class=HTMLResponse)
async def admin_panel():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Passaire Admin</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #0f0f1a; color: #e0e0f0; min-height: 100vh; padding: 32px;
    }
    h1   { font-size: 28px; color: #fff; margin-bottom: 8px; }
    .sub { color: #888; margin-bottom: 40px; font-size: 14px; }

    .card {
      background: #1a1a2e; border: 1px solid #2a2a4a;
      border-radius: 12px; padding: 24px; margin-bottom: 24px;
    }
    h2 { font-size: 17px; margin-bottom: 16px; color: #a0a0ff; }

    label { display: block; font-size: 13px; color: #888; margin-bottom: 5px; margin-top: 10px; }
    label:first-child { margin-top: 0; }

    input, select, textarea {
      width: 100%; padding: 10px 14px;
      background: #0f0f1a; border: 1px solid #333;
      border-radius: 8px; color: #fff; font-size: 14px;
    }
    textarea { resize: vertical; }

    button {
      margin-top: 14px;
      background: #5B3BE8; color: #fff; border: none;
      border-radius: 8px; padding: 11px 22px;
      cursor: pointer; font-size: 14px; font-weight: 600;
      transition: background .15s;
    }
    button:hover { background: #7055f0; }
    button.danger { background: #c0392b; }
    button.danger:hover { background: #e74c3c; }

    .result {
      background: #0a1628; border: 1px solid #1e3a5f;
      border-radius: 8px; padding: 14px; font-size: 13px;
      font-family: monospace; white-space: pre-wrap;
      color: #4ADE00; margin-top: 12px; display: none;
    }
    .result.error { color: #f87171; border-color: #7f1d1d; }

    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
    @media(max-width: 760px) { .grid { grid-template-columns: 1fr; } }

    .badge {
      display: inline-block; padding: 2px 8px; border-radius: 10px;
      font-size: 12px; font-weight: 600;
    }
    .b-invited   { background:#1e3a5f; color:#60a5fa; }
    .b-confirmed { background:#064e3b; color:#34d399; }
    .b-declined  { background:#4c0519; color:#f87171; }
    .b-checked_in{ background:#3b1f06; color:#fb923c; }

    table { width:100%; border-collapse:collapse; margin-top:12px; font-size:13px; }
    th { text-align:left; color:#666; padding:6px 10px; border-bottom:1px solid #2a2a4a; font-weight:500; }
    td { padding:8px 10px; border-bottom:1px solid #1a1a2e; vertical-align: middle; }
    tr:hover td { background:#1f1f35; }

    button:disabled { opacity: .55; cursor: not-allowed; }
    button.small { padding: 7px 14px; font-size: 13px; margin-top: 0; }

    .card h2 .count {
      font-size: 12px; color: #666; font-weight: 500; margin-left: 6px;
    }

    /* ── Events list view ── */
    .events-grid {
      display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 16px; margin-bottom: 24px;
    }
    .event-card {
      background: #1a1a2e; border: 1px solid #2a2a4a; border-radius: 12px;
      padding: 18px; cursor: pointer; transition: border-color .15s, transform .1s;
    }
    .event-card:hover { border-color: #5B3BE8; transform: translateY(-2px); }
    .event-card h3 { font-size: 16px; color: #fff; margin-bottom: 6px; }
    .event-card-meta { font-size: 12px; color: #888; margin-bottom: 10px; }
    .event-card-stats { display: flex; gap: 12px; font-size: 12px; color: #a0a0ff; flex-wrap: wrap; }

    .summary-header {
      display: flex; justify-content: space-between; align-items: center; cursor: pointer;
    }
    .summary-header h2 { margin: 0; }
    .summary-stats { display: flex; gap: 28px; flex-wrap: wrap; margin-top: 14px; }
    .stat-num { font-size: 24px; font-weight: 700; color: #fff; }
    .stat-label { font-size: 12px; color: #888; margin-top: 2px; }

    /* ── Event detail view ── */
    .tab-strip {
      display: flex; gap: 4px; flex-wrap: wrap;
      border-bottom: 1px solid #2a2a4a; margin-bottom: 16px;
    }
    .tab-btn {
      margin: 0; background: transparent; color: #888; border: none; border-radius: 8px 8px 0 0;
      padding: 10px 16px; font-size: 13px; font-weight: 600; border-bottom: 2px solid transparent;
    }
    .tab-btn:hover { background: #1a1a2e; color: #ccc; }
    .tab-btn.active { color: #a0a0ff; border-bottom-color: #5B3BE8; }

    .b-sent       { background:#1e3a5f; color:#60a5fa; }
    .b-delivered  { background:#064e3b; color:#34d399; }
    .b-read       { background:#1e3a5f; color:#818cf8; }
    .b-failed     { background:#4c0519; color:#f87171; }
    .b-bounced    { background:#4c0519; color:#fb923c; }
    .b-complained { background:#4c0519; color:#fca5a5; }
    .b-queued     { background:#292524; color:#a8a29e; }

    .edit-email-btn { background: transparent; padding: 2px 6px; margin: 0 0 0 4px; font-size: 11px; }

    details.legacy-details { margin-top: 8px; }
    details.legacy-details summary {
      cursor: pointer; color: #666; font-size: 13px; padding: 10px 0; user-select: none;
    }
    details.legacy-details summary:hover { color: #999; }
  </style>
</head>
<body>
  <h1>🎟️ Passaire Admin</h1>
  <p class="sub">Event management & WhatsApp/email ticketing dashboard</p>

  <!-- ══════════════════════ EVENTS LIST VIEW ══════════════════════ -->
  <div id="view-list">

    <div class="card" id="summary-card">
      <div class="summary-header" onclick="toggleSummary()">
        <h2>📊 All Events Summary</h2>
        <span id="summary-toggle-icon">▾</span>
      </div>
      <div id="summary-body"></div>
    </div>

    <div class="card">
      <h2>➕ Create Event</h2>
      <label>Event Name</label>
      <input id="ev-name" placeholder="Move Beyond Night">
      <label>Date</label>
      <input id="ev-date" type="date">
      <label>Venue</label>
      <input id="ev-venue" placeholder="Cairo Jazz Club">
      <label>Gate Count</label>
      <input id="ev-gates" type="number" value="1" min="1">
      <button onclick="withLoading(this, createEvent)">Create Event</button>
      <div class="result" id="ev-result"></div>
    </div>

    <div id="events-grid" class="events-grid"></div>

    <details class="legacy-details">
      <summary>⚙️ Legacy tools (Green API, test email)</summary>

      <div class="card">
        <h2>✉️ Send Test Email</h2>
        <p style="font-size:13px;color:#888;margin-bottom:4px;">
          Verify the Resend integration (movetick@mbeg.org) is working.
        </p>
        <label>To</label>
        <input id="email-test-to" placeholder="you@example.com">
        <button onclick="withLoading(this, sendTestEmail)">Send Test Email</button>
        <div class="result" id="email-test-result"></div>
      </div>

      <div class="card">
        <h2>🔗 Setup Green API Webhook</h2>
        <p style="font-size:13px;color:#888;margin-bottom:4px;">
          Legacy WhatsApp channel — superseded by the Cloud API for admin-triggered
          sends, kept as a manual fallback. Run once after deployment to connect
          Green API to this backend.
        </p>
        <button onclick="withLoading(this, setupWebhook)">Register Webhook</button>
        <div class="result" id="wh-result"></div>
      </div>
    </details>
  </div>

  <!-- ══════════════════════ EVENT DETAIL VIEW ══════════════════════ -->
  <div id="view-detail" style="display:none">
    <button class="small" onclick="navigate('#/')" style="margin-bottom:16px">← All Events</button>

    <div class="card" id="detail-header"></div>

    <div class="tab-strip" id="detail-tabs">
      <button class="tab-btn" data-tab="stats"       onclick="showTab('stats')">📊 Stats</button>
      <button class="tab-btn" data-tab="guests"       onclick="showTab('guests')">👥 Guests</button>
      <button class="tab-btn" data-tab="upload"       onclick="showTab('upload')">📋 Upload</button>
      <button class="tab-btn" data-tab="invite"       onclick="showTab('invite')">📨 Invitations</button>
      <button class="tab-btn" data-tab="email"        onclick="showTab('email')">✉️ Email</button>
      <button class="tab-btn" data-tab="reminder"     onclick="showTab('reminder')">🔔 Reminder</button>
      <button class="tab-btn" data-tab="deliverylog"  onclick="showTab('deliverylog')">📬 Delivery Log</button>
    </div>

    <div class="tab-panel card" id="tab-stats">
      <h2>📊 Live Stats</h2>
      <button class="small" onclick="withLoading(this, fetchStats)">Refresh</button>
      <div class="result" id="stat-result"></div>
    </div>

    <div class="tab-panel card" id="tab-guests" style="display:none">
      <h2>👥 Guest List<span class="count" id="gl-count"></span></h2>
      <input id="gl-search" placeholder="🔍 Search by name, phone, or email…" oninput="filterGuests()">
      <div id="gl-table"></div>
    </div>

    <div class="tab-panel card" id="tab-upload" style="display:none">
      <h2>📋 Upload Guest List</h2>
      <a href="/guests/template" download style="color:#a0a0ff;font-size:13px;display:inline-block;margin-bottom:12px">⬇ Download Template</a>
      <label>CSV / Excel — columns: name, phone, email, zone (email, zone optional)</label>
      <input id="ul-file" type="file" accept=".csv,.xlsx,.xls">

      <label style="margin-top:14px">Send Mode</label>
      <div style="display:flex;gap:0;border:1px solid #333;border-radius:8px;overflow:hidden;margin-bottom:4px;">
        <button id="mode-rsvp" onclick="setMode('rsvp')"
          style="flex:1;margin:0;border-radius:0;background:#5B3BE8;border-right:1px solid #333">
          💬 RSVP First
        </button>
        <button id="mode-direct" onclick="setMode('direct')"
          style="flex:1;margin:0;border-radius:0;background:#1a1a2e">
          ⚡ Direct QR
        </button>
      </div>
      <p id="mode-desc" style="font-size:12px;color:#888;margin-bottom:10px">
        Guests receive invitation → reply 1 to get QR ticket
      </p>

      <button onclick="withLoading(this, uploadGuests)">Upload &amp; Send</button>
      <div class="result" id="ul-result"></div>
    </div>

    <div class="tab-panel card" id="tab-invite" style="display:none">
      <h2>📨 Send WhatsApp Invitations</h2>
      <p style="font-size:13px;color:#888;margin-bottom:4px;">
        WhatsApp Cloud API requires a pre-approved Meta template for this to work.
      </p>
      <label>Template Name</label>
      <input id="inv-template" placeholder="e.g. event_invitation_v1">
      <label>Language</label>
      <input id="inv-lang" value="en_US">
      <label>Body Params (comma-separated — supports {name} {event_name} {event_date} {venue})</label>
      <input id="inv-params" placeholder="{name}, {event_name}, {event_date}">
      <label>Image URL (optional)</label>
      <input id="inv-image" placeholder="https://…">
      <button onclick="withLoading(this, sendInvitations)">Send to All Invited Guests</button>
      <div class="result" id="inv-result"></div>
    </div>

    <div class="tab-panel card" id="tab-email" style="display:none">
      <h2>✉️ Send Bulk Email</h2>
      <label>Target Audience</label>
      <select id="bulk-email-target">
        <option value="invited">Invited</option>
        <option value="confirmed">Confirmed</option>
        <option value="all">All</option>
      </select>
      <label>Subject</label>
      <input id="bulk-email-subject" placeholder="You're invited!">
      <label>HTML Body (use {name}, {event_name}, {event_date})</label>
      <textarea id="bulk-email-html" rows="6" placeholder="&lt;p&gt;Hi {name}, …&lt;/p&gt;"></textarea>
      <button onclick="withLoading(this, sendBulkEmail)">Send</button>
      <div class="result" id="bulk-email-result"></div>
    </div>

    <div class="tab-panel card" id="tab-reminder" style="display:none">
      <h2>🔔 Send Bulk Reminder</h2>
      <p style="font-size:13px;color:#888;margin-bottom:4px;">
        WhatsApp Cloud API requires a pre-approved Meta template for this to work.
      </p>
      <label>Template Name</label>
      <input id="rem-template" placeholder="e.g. event_reminder_v1">
      <label>Language</label>
      <input id="rem-lang" value="en_US">
      <label>Body Params (comma-separated)</label>
      <input id="rem-params" placeholder="{name}, {event_date}">
      <label>Image URL (optional)</label>
      <input id="rem-image" placeholder="https://…">
      <button onclick="withLoading(this, sendReminder)">Send to All Confirmed Guests</button>
      <div class="result" id="rem-result"></div>
    </div>

    <div class="tab-panel card" id="tab-deliverylog" style="display:none">
      <h2>📬 Delivery Log</h2>
      <button class="small" onclick="withLoading(this, loadDeliveryLog)">Refresh</button>
      <div id="deliverylog-table"></div>
    </div>
  </div>

<script>
const api = "";
let currentEventId = null;
let currentEvent   = null;
let _guestData     = [];
let _tabLoaded     = {};
let summaryExpanded = localStorage.getItem("summaryExpanded") !== "false";

// ── helpers ──────────────────────────────────────────────────────────────────
function show(id, data, isError = false) {
  const el = document.getElementById(id);
  el.className = "result" + (isError ? " error" : "");
  el.style.display = "block";
  el.textContent = typeof data === "string" ? data : JSON.stringify(data, null, 2);
}

async function call(url, opts = {}) {
  const r = await fetch(api + url, opts);
  const d = await r.json().catch(() => ({ error: "non-JSON response" }));
  return { ok: r.ok, data: d };
}

async function withLoading(btn, fn) {
  const orig = btn.textContent;
  btn.disabled = true;
  btn.textContent = "⏳ Working…";
  try {
    await fn();
  } finally {
    btn.disabled = false;
    btn.textContent = orig;
  }
}

function parseParams(str) {
  return str.split(",").map(s => s.trim()).filter(Boolean);
}

// ── routing ──────────────────────────────────────────────────────────────────
window.addEventListener("hashchange", router);

function navigate(hash) { location.hash = hash; }

function router() {
  const m = (location.hash || "#/").match(/^#[/]event[/]([a-f0-9-]+)$/i);
  if (m) showDetailView(m[1]); else showListView();
}

// ── list view ────────────────────────────────────────────────────────────────
async function showListView() {
  document.getElementById("view-detail").style.display = "none";
  document.getElementById("view-list").style.display = "block";
  await loadSummary();
}

function toggleSummary() {
  summaryExpanded = !summaryExpanded;
  localStorage.setItem("summaryExpanded", summaryExpanded);
  applySummaryVisibility();
}

function applySummaryVisibility() {
  document.getElementById("summary-body").style.display = summaryExpanded ? "block" : "none";
  document.getElementById("summary-toggle-icon").textContent = summaryExpanded ? "▾" : "▸";
}

async function loadSummary() {
  const { ok, data } = await call("/events/summary");
  applySummaryVisibility();
  if (!ok) {
    document.getElementById("summary-body").innerHTML = '<p style="color:#f87171">Failed to load summary</p>';
    document.getElementById("events-grid").innerHTML = "";
    return;
  }
  renderSummaryBar(data.grand_totals);
  renderEventsGrid(data.events);
}

function renderSummaryBar(g) {
  document.getElementById("summary-body").innerHTML = `
    <div class="summary-stats">
      <div><div class="stat-num">${g.events}</div><div class="stat-label">Events</div></div>
      <div><div class="stat-num">${g.guest_count}</div><div class="stat-label">Guests</div></div>
      <div><div class="stat-num">${g.checked_in}</div><div class="stat-label">Checked In</div></div>
      <div><div class="stat-num">${g.messages_sent}</div><div class="stat-label">Sent</div></div>
      <div><div class="stat-num" style="color:#f87171">${g.messages_failed}</div><div class="stat-label">Failed</div></div>
      <div><div class="stat-num" style="color:#fb923c">${g.messages_bounced}</div><div class="stat-label">Bounced</div></div>
    </div>`;
}

function renderEventsGrid(events) {
  const grid = document.getElementById("events-grid");
  if (!events.length) {
    grid.innerHTML = '<p style="color:#888">No events yet — create one above.</p>';
    return;
  }
  grid.innerHTML = events.map(e => `
    <div class="event-card" onclick="navigate('#/event/${e.id}')">
      <h3>${e.name}</h3>
      <div class="event-card-meta">${e.date}${e.venue ? " · " + e.venue : ""}</div>
      <div class="event-card-stats">
        <span>👥 ${e.guest_count}</span>
        <span>✅ ${e.checked_in} in</span>
        ${e.messages_failed > 0 ? `<span style="color:#f87171">⚠ ${e.messages_failed} failed</span>` : ""}
        ${e.messages_bounced > 0 ? `<span style="color:#fb923c">↩ ${e.messages_bounced} bounced</span>` : ""}
      </div>
    </div>`).join("");
}

// ── detail view ──────────────────────────────────────────────────────────────
async function showDetailView(eventId) {
  const { ok, data } = await call(`/events/${eventId}`);
  if (!ok) { navigate("#/"); return; }
  currentEventId = eventId;
  currentEvent = data;
  _tabLoaded = {};
  document.getElementById("view-list").style.display = "none";
  document.getElementById("view-detail").style.display = "block";
  renderDetailHeader(data);
  showTab("stats");
}

function renderDetailHeader(ev) {
  document.getElementById("detail-header").innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px">
      <div>
        <h2 style="margin-bottom:4px">${ev.name}</h2>
        <div style="color:#888;font-size:13px">${ev.date}${ev.venue ? " · " + ev.venue : ""} · ${ev.gate_count || 1} gate(s)</div>
      </div>
      <button class="small" onclick="toggleEditEvent()">✎ Edit</button>
    </div>
    <div id="edit-event-form" style="display:none;margin-top:16px;border-top:1px solid #2a2a4a;padding-top:16px">
      <label>Name</label><input id="edit-ev-name" value="${(ev.name || "").replace(/"/g, "&quot;")}">
      <label>Date</label><input id="edit-ev-date" type="date" value="${ev.date}">
      <label>Venue</label><input id="edit-ev-venue" value="${(ev.venue || "").replace(/"/g, "&quot;")}">
      <label>Gate Count</label><input id="edit-ev-gates" type="number" min="1" value="${ev.gate_count || 1}">
      <button onclick="withLoading(this, saveEventEdit)">💾 Save</button>
      <button class="small" style="background:#333" onclick="toggleEditEvent()">Cancel</button>
      <div class="result" id="edit-ev-result"></div>
    </div>`;
}

function toggleEditEvent() {
  const f = document.getElementById("edit-event-form");
  f.style.display = f.style.display === "none" ? "block" : "none";
}

async function saveEventEdit() {
  const body = {
    name: document.getElementById("edit-ev-name").value.trim(),
    date: document.getElementById("edit-ev-date").value,
    venue: document.getElementById("edit-ev-venue").value.trim(),
    gate_count: parseInt(document.getElementById("edit-ev-gates").value) || 1,
  };
  const { ok, data } = await call(`/events/${currentEventId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  show("edit-ev-result", data, !ok);
  if (ok) { currentEvent = data; renderDetailHeader(data); }
}

// ── tabs ─────────────────────────────────────────────────────────────────────
const TAB_LOADERS = { stats: fetchStats, guests: loadGuests, deliverylog: loadDeliveryLog };

function showTab(name) {
  document.querySelectorAll(".tab-panel").forEach(p => p.style.display = "none");
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
  document.getElementById("tab-" + name).style.display = "block";
  if (!_tabLoaded[name] && TAB_LOADERS[name]) {
    _tabLoaded[name] = true;
    TAB_LOADERS[name]();
  }
}

// ── create event ─────────────────────────────────────────────────────────────
async function createEvent() {
  const body = {
    name: document.getElementById("ev-name").value.trim(),
    date: document.getElementById("ev-date").value,
    venue: document.getElementById("ev-venue").value.trim(),
    gate_count: parseInt(document.getElementById("ev-gates").value) || 1,
  };
  if (!body.name || !body.date) return show("ev-result", "Name and date are required", true);
  const { ok, data } = await call("/events/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  show("ev-result", data, !ok);
  if (ok && data.id) navigate("#/event/" + data.id);
}

// ── send mode toggle ─────────────────────────────────────────────────────────
let _sendMode = "rsvp";
function setMode(m) {
  _sendMode = m;
  document.getElementById("mode-rsvp").style.background   = m === "rsvp"   ? "#5B3BE8" : "#1a1a2e";
  document.getElementById("mode-direct").style.background = m === "direct" ? "#5B3BE8" : "#1a1a2e";
  document.getElementById("mode-desc").textContent = m === "rsvp"
    ? "Guests receive invitation → reply 1 to get QR ticket"
    : "⚡ QR ticket generated & sent instantly — no reply needed";
}

// ── upload ───────────────────────────────────────────────────────────────────
async function uploadGuests() {
  const file = document.getElementById("ul-file").files[0];
  if (!file) return show("ul-result", "Choose a file", true);
  if (!confirm(`Upload "${file.name}" and send ${_sendMode === "direct" ? "QR tickets" : "RSVP invitations"} to every guest in it?`)) return;
  const fd = new FormData();
  fd.append("event_id", currentEventId);
  fd.append("send_mode", _sendMode);
  fd.append("file", file);
  const { ok, data } = await call("/guests/upload", { method: "POST", body: fd });
  show("ul-result", data, !ok);
  if (ok) { _tabLoaded.guests = false; loadGuests(); }
}

// ── guests ───────────────────────────────────────────────────────────────────
function deliveryBadge(d) {
  if (!d) return '<span style="color:#555">—</span>';
  return `<span class="badge b-${d.status}">${d.channel === "whatsapp" ? "💬" : "✉️"} ${d.status}</span>`;
}

function renderGuestTable(rows) {
  if (!rows.length) {
    document.getElementById("gl-table").innerHTML =
      '<p style="color:#888;margin-top:12px">No matching guests.</p>';
    return;
  }
  const statusBadge = (s) => `<span class="badge b-${s}">${s}</span>`;
  const html = rows.map((g, i) => `
    <tr>
      <td style="color:#555">${i + 1}</td>
      <td>${g.name}</td>
      <td style="font-family:monospace;color:#94a3b8">${g.phone}</td>
      <td class="email-cell" data-guest-id="${g.id}">${g.email || '<span style="color:#555">—</span>'}<button class="edit-email-btn" onclick="editEmail('${g.id}')">✎</button></td>
      <td>${statusBadge(g.status)}</td>
      <td>${deliveryBadge(g.delivery)}</td>
    </tr>`).join("");
  document.getElementById("gl-table").innerHTML = `
    <table>
      <thead><tr><th>#</th><th>Name</th><th>Phone</th><th>Email</th><th>Status</th><th>Delivery</th></tr></thead>
      <tbody>${html}</tbody>
    </table>`;
}

function editEmail(guestId) {
  const td = document.querySelector(`.email-cell[data-guest-id="${guestId}"]`);
  const guest = _guestData.find(g => g.id === guestId);
  td.innerHTML = `<input type="email" value="${guest.email || ""}" style="width:180px;display:inline-block;padding:4px 8px" id="email-input-${guestId}">
    <button onclick="saveEmail('${guestId}')" class="small" style="padding:4px 8px">💾</button>`;
  document.getElementById(`email-input-${guestId}`).focus();
}

async function saveEmail(guestId) {
  const input = document.getElementById(`email-input-${guestId}`);
  const email = input.value.trim();
  const { ok, data } = await call(`/guests/detail/${guestId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (ok) {
    const guest = _guestData.find(g => g.id === guestId);
    guest.email = data.email;
    filterGuests();
  } else {
    alert("Failed to save email: " + JSON.stringify(data));
  }
}

function filterGuests() {
  const q = document.getElementById("gl-search").value.trim().toLowerCase();
  if (!q) return renderGuestTable(_guestData);
  renderGuestTable(_guestData.filter(g =>
    (g.name || "").toLowerCase().includes(q) ||
    (g.phone || "").toLowerCase().includes(q) ||
    (g.email || "").toLowerCase().includes(q)
  ));
}

async function loadGuests() {
  const countEl = document.getElementById("gl-count");
  const { ok, data } = await call(`/guests/${currentEventId}`);
  if (!ok || !Array.isArray(data)) {
    document.getElementById("gl-table").innerHTML =
      '<p style="color:#f87171;margin-top:12px">Error loading guests</p>';
    countEl.textContent = "";
    return;
  }
  _guestData = data;
  countEl.textContent = `(${data.length})`;
  document.getElementById("gl-search").value = "";
  renderGuestTable(_guestData);
}

// ── invitations (Cloud API) ─────────────────────────────────────────────────
async function sendInvitations() {
  const template_name = document.getElementById("inv-template").value.trim();
  if (!template_name) return show("inv-result", "Enter a template name", true);
  if (!confirm(`Send WhatsApp invitations (template "${template_name}") to every invited guest of "${currentEvent.name}"? This messages real people.`)) return;
  const body = {
    event_id: currentEventId,
    template_name,
    language: document.getElementById("inv-lang").value.trim() || "en_US",
    body_params: parseParams(document.getElementById("inv-params").value),
    image_url: document.getElementById("inv-image").value.trim() || null,
  };
  const { ok, data } = await call("/whatsapp-cloud/send-invitations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  show("inv-result", data, !ok);
}

// ── reminder (Cloud API) ─────────────────────────────────────────────────────
async function sendReminder() {
  const template_name = document.getElementById("rem-template").value.trim();
  if (!template_name) return show("rem-result", "Enter a template name", true);
  if (!confirm(`Send this reminder (template "${template_name}") to every CONFIRMED guest of "${currentEvent.name}"? This messages real people.`)) return;
  const body = {
    event_id: currentEventId,
    template_name,
    language: document.getElementById("rem-lang").value.trim() || "en_US",
    body_params: parseParams(document.getElementById("rem-params").value),
    image_url: document.getElementById("rem-image").value.trim() || null,
  };
  const { ok, data } = await call("/whatsapp-cloud/send-reminder", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  show("rem-result", data, !ok);
}

// ── bulk email ───────────────────────────────────────────────────────────────
async function sendBulkEmail() {
  const subject = document.getElementById("bulk-email-subject").value.trim();
  const html_template = document.getElementById("bulk-email-html").value.trim();
  const target_status = document.getElementById("bulk-email-target").value;
  if (!subject || !html_template) return show("bulk-email-result", "Fill in subject and body", true);
  if (!confirm(`Send this email to ${target_status === "all" ? "ALL" : target_status.toUpperCase()} guests of "${currentEvent.name}" with an email on file? This messages real people.`)) return;
  const { ok, data } = await call("/email/send-bulk", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event_id: currentEventId, subject, html_template, target_status }),
  });
  show("bulk-email-result", data, !ok);
}

// ── stats ────────────────────────────────────────────────────────────────────
async function fetchStats() {
  const { ok, data } = await call(`/scanner/live/${currentEventId}`);
  show("stat-result", data, !ok);
}

// ── delivery log ─────────────────────────────────────────────────────────────
async function loadDeliveryLog() {
  const { ok, data } = await call(`/events/${currentEventId}/delivery-log?limit=100`);
  const el = document.getElementById("deliverylog-table");
  if (!ok || !Array.isArray(data)) {
    el.innerHTML = '<p style="color:#f87171">Error loading delivery log</p>';
    return;
  }
  if (!data.length) {
    el.innerHTML = '<p style="color:#888">No messages sent yet.</p>';
    return;
  }
  const rows = data.map(r => `
    <tr>
      <td>${r.guest_name || "—"}</td>
      <td>${r.channel === "whatsapp" ? "💬 WhatsApp" : "✉️ Email"}</td>
      <td>${r.message_type}</td>
      <td><span class="badge b-${r.status}">${r.status}</span></td>
      <td style="color:#f87171;font-size:12px">${r.error_detail || ""}</td>
      <td style="color:#666;font-size:12px">${new Date(r.created_at).toLocaleString()}</td>
    </tr>`).join("");
  el.innerHTML = `
    <table>
      <thead><tr><th>Guest</th><th>Channel</th><th>Type</th><th>Status</th><th>Error</th><th>When</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

// ── legacy: test email ──────────────────────────────────────────────────────
async function sendTestEmail() {
  const to = document.getElementById("email-test-to").value.trim();
  if (!to) return show("email-test-result", "Enter a recipient email", true);
  const { ok, data } = await call("/email/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ to }),
  });
  show("email-test-result", data, !ok);
}

// ── legacy: green api webhook ───────────────────────────────────────────────
async function setupWebhook() {
  const { ok, data } = await call("/setup-webhook", { method: "POST" });
  show("wh-result", data, !ok);
}

// ── init ─────────────────────────────────────────────────────────────────────
router();
</script>
</body>
</html>
"""
