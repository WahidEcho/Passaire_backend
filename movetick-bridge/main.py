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
    td { padding:8px 10px; border-bottom:1px solid #1a1a2e; }
    tr:hover td { background:#1f1f35; }

    /* ── Active event bar ── */
    .event-bar {
      background: #1a1a2e; border: 1px solid #5B3BE8;
      border-radius: 12px; padding: 18px 24px; margin-bottom: 24px;
      display: flex; gap: 16px; align-items: center; flex-wrap: wrap;
      position: sticky; top: 12px; z-index: 10;
      box-shadow: 0 8px 24px rgba(0,0,0,.35);
    }
    .event-bar label { margin: 0; white-space: nowrap; }
    .event-bar select { min-width: 260px; width: auto; }
    #active-event-banner {
      font-size: 13px; color: #a0a0ff; flex: 1; min-width: 200px;
    }
    #active-event-banner.empty { color: #666; font-style: italic; }

    button:disabled { opacity: .55; cursor: not-allowed; }
    button.small { padding: 7px 14px; font-size: 13px; margin-top: 0; }

    .card h2 .count {
      font-size: 12px; color: #666; font-weight: 500; margin-left: 6px;
    }
  </style>
</head>
<body>
  <h1>🎟️ Passaire Admin</h1>
  <p class="sub">Event management & WhatsApp ticketing dashboard</p>

  <!-- ── Active Event Selector (drives every Event ID field below) ── -->
  <div class="event-bar">
    <label style="margin:0">Active Event</label>
    <select id="active-event-select" onchange="onEventChange(true)">
      <option value="">— Loading events… —</option>
    </select>
    <button class="small" onclick="loadEventsList()" title="Refresh event list">⟳</button>
    <div id="active-event-banner" class="empty">No event selected — pick one to auto-fill every panel below.</div>
  </div>

  <div class="grid">

    <!-- ── Create Event ── -->
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

    <!-- ── Upload Guests ── -->
    <div class="card">
      <h2>📋 Upload Guest List</h2>
      <label>Event ID</label>
      <input id="ul-event-id" class="event-id-field" placeholder="Select an active event above, or paste a UUID">
      <label>CSV / Excel — columns: name, phone, zone (zone optional)</label>
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

    <!-- ── Send Invitations ── -->
    <div class="card">
      <h2>📨 Send WhatsApp Invitations</h2>
      <label>Event ID</label>
      <input id="inv-event-id" class="event-id-field" placeholder="Select an active event above, or paste a UUID">
      <button onclick="withLoading(this, sendInvitations)">Send to All Invited Guests</button>
      <div class="result" id="inv-result"></div>
    </div>

    <!-- ── Send Reminder ── -->
    <div class="card">
      <h2>🔔 Send Bulk Reminder / Agenda</h2>
      <label>Event ID</label>
      <input id="rem-event-id" class="event-id-field" placeholder="Select an active event above, or paste a UUID">
      <label>Message (use {name} for personalisation)</label>
      <textarea id="rem-msg" rows="4" placeholder="Hi {name}! Reminder: event starts at 8pm…"></textarea>
      <button onclick="withLoading(this, sendReminder)">Send to All Confirmed Guests</button>
      <div class="result" id="rem-result"></div>
    </div>

    <!-- ── Live Stats ── -->
    <div class="card">
      <h2>📊 Live Stats</h2>
      <label>Event ID</label>
      <input id="stat-event-id" class="event-id-field" placeholder="Select an active event above, or paste a UUID">
      <button onclick="withLoading(this, fetchStats)">Refresh Stats</button>
      <div class="result" id="stat-result"></div>
    </div>

    <!-- ── Send Test Email ── -->
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

    <!-- ── Setup Webhook ── -->
    <div class="card">
      <h2>🔗 Setup Green API Webhook</h2>
      <p style="font-size:13px;color:#888;margin-bottom:4px;">
        Run once after deployment to connect Green API (legacy WhatsApp channel) to this backend.
        The WhatsApp Cloud API webhook is configured separately in the Meta App Dashboard.
      </p>
      <button onclick="withLoading(this, setupWebhook)">Register Webhook</button>
      <div class="result" id="wh-result"></div>
    </div>

  </div>

  <!-- ── Guest List Table ── -->
  <div class="card">
    <h2>👥 Guest List<span class="count" id="gl-count"></span></h2>
    <label>Event ID</label>
    <div style="display:flex;gap:10px;align-items:flex-end;">
      <input id="gl-event-id" class="event-id-field" placeholder="Select an active event above, or paste a UUID" style="flex:1">
      <button class="small" onclick="withLoading(this, loadGuests)" style="margin-top:0">Load Guests</button>
    </div>
    <input id="gl-search" placeholder="🔍 Search by name or phone…" style="margin-top:12px" oninput="filterGuests()">
    <div id="gl-table"></div>
  </div>

<script>
const api = "";
let EVENTS = [];
let currentEventId = localStorage.getItem("activeEventId") || "";
let _guestData = [];

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

// ── active event selector ───────────────────────────────────────────────────
async function loadEventsList() {
  const { ok, data } = await call("/events/");
  const sel = document.getElementById("active-event-select");
  if (!ok || !Array.isArray(data)) {
    sel.innerHTML = '<option value="">— Failed to load events —</option>';
    return;
  }
  EVENTS = data;
  sel.innerHTML = '<option value="">— Select an event —</option>' +
    data.map(e => `<option value="${e.id}">${e.name} — ${e.date}</option>`).join("");
  if (currentEventId && data.some(e => e.id === currentEventId)) {
    sel.value = currentEventId;
    onEventChange(false);
  }
}

function onEventChange(userInitiated) {
  const sel = document.getElementById("active-event-select");
  currentEventId = sel.value;
  localStorage.setItem("activeEventId", currentEventId);
  document.querySelectorAll(".event-id-field").forEach(el => el.value = currentEventId);

  const banner = document.getElementById("active-event-banner");
  const ev = EVENTS.find(e => e.id === currentEventId);
  if (ev) {
    banner.className = "";
    banner.innerHTML = `📍 <strong>${ev.name}</strong> — ${ev.date}` +
      (ev.venue ? ` @ ${ev.venue}` : "") +
      ` <span style="color:#666">(${ev.gate_count || 1} gate${(ev.gate_count || 1) > 1 ? "s" : ""})</span>`;
    fetchStats();
    loadGuests();
  } else {
    banner.className = "empty";
    banner.textContent = "No event selected — pick one to auto-fill every panel below.";
  }
}

// ── event ─────────────────────────────────────────────────────────────────────
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
  if (ok) {
    await loadEventsList();
    if (data.id) {
      document.getElementById("active-event-select").value = data.id;
      onEventChange(true);
    }
  }
}

// ── send mode toggle ──────────────────────────────────────────────────────────
let _sendMode = "rsvp";
function setMode(m) {
  _sendMode = m;
  document.getElementById("mode-rsvp").style.background   = m === "rsvp"   ? "#5B3BE8" : "#1a1a2e";
  document.getElementById("mode-direct").style.background = m === "direct" ? "#5B3BE8" : "#1a1a2e";
  document.getElementById("mode-desc").textContent = m === "rsvp"
    ? "Guests receive invitation → reply 1 to get QR ticket"
    : "⚡ QR ticket generated & sent instantly — no reply needed";
}

// ── guests ───────────────────────────────────────────────────────────────────
async function uploadGuests() {
  const eventId = document.getElementById("ul-event-id").value.trim();
  const file = document.getElementById("ul-file").files[0];
  if (!file || !eventId) return show("ul-result", "Fill in event ID and choose a file", true);
  if (!confirm(`Upload "${file.name}" and send ${_sendMode === "direct" ? "QR tickets" : "RSVP invitations"} to every guest in it?`)) return;
  const fd = new FormData();
  fd.append("event_id", eventId);
  fd.append("send_mode", _sendMode);
  fd.append("file", file);
  const { ok, data } = await call("/guests/upload", { method: "POST", body: fd });
  show("ul-result", data, !ok);
  if (ok) loadGuests();
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
      <td>${statusBadge(g.status)}</td>
    </tr>`).join("");
  document.getElementById("gl-table").innerHTML = `
    <table>
      <thead><tr><th>#</th><th>Name</th><th>Phone</th><th>Status</th></tr></thead>
      <tbody>${html}</tbody>
    </table>`;
}

function filterGuests() {
  const q = document.getElementById("gl-search").value.trim().toLowerCase();
  if (!q) return renderGuestTable(_guestData);
  renderGuestTable(_guestData.filter(g =>
    (g.name || "").toLowerCase().includes(q) || (g.phone || "").toLowerCase().includes(q)
  ));
}

async function loadGuests() {
  const eventId = document.getElementById("gl-event-id").value.trim();
  const countEl = document.getElementById("gl-count");
  if (!eventId) {
    document.getElementById("gl-table").innerHTML = "";
    countEl.textContent = "";
    return;
  }
  const { ok, data } = await call(`/guests/${eventId}`);
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

// ── invitations ───────────────────────────────────────────────────────────────
async function sendInvitations() {
  const eventId = document.getElementById("inv-event-id").value.trim();
  if (!eventId) return show("inv-result", "Enter event ID", true);
  const ev = EVENTS.find(e => e.id === eventId);
  if (!confirm(`Send WhatsApp invitations to every invited guest of "${ev ? ev.name : eventId}"? This messages real people and can't be undone.`)) return;
  const { ok, data } = await call("/whatsapp/send-invitations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event_id: eventId }),
  });
  show("inv-result", data, !ok);
}

// ── reminder ──────────────────────────────────────────────────────────────────
async function sendReminder() {
  const eventId = document.getElementById("rem-event-id").value.trim();
  const message = document.getElementById("rem-msg").value.trim();
  if (!eventId || !message) return show("rem-result", "Fill in event ID and message", true);
  const ev = EVENTS.find(e => e.id === eventId);
  if (!confirm(`Send this reminder to every CONFIRMED guest of "${ev ? ev.name : eventId}"? This messages real people and can't be undone.`)) return;
  const { ok, data } = await call("/whatsapp/send-reminder", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event_id: eventId, message }),
  });
  show("rem-result", data, !ok);
}

// ── stats ─────────────────────────────────────────────────────────────────────
async function fetchStats() {
  const eventId = document.getElementById("stat-event-id").value.trim();
  if (!eventId) return show("stat-result", "Enter event ID", true);
  const { ok, data } = await call(`/scanner/live/${eventId}`);
  show("stat-result", data, !ok);
}

// ── test email ───────────────────────────────────────────────────────────────
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

// ── webhook ───────────────────────────────────────────────────────────────────
async function setupWebhook() {
  const { ok, data } = await call("/setup-webhook", { method: "POST" });
  show("wh-result", data, !ok);
}

// ── init ─────────────────────────────────────────────────────────────────────
loadEventsList();
</script>
</body>
</html>
"""
