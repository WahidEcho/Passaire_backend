-- ============================================================
-- PASSAIRE — FULL SCHEMA  (copy-paste into Supabase SQL Editor)
-- ============================================================

-- 1. EVENTS
create table p_events (
  id               uuid primary key default gen_random_uuid(),
  name             text not null,
  date             date not null,
  venue            text,
  gate_count       int  default 1,
  slug             text unique,           -- human-readable id e.g. "moharram-partners"
  manager_passcode text,                  -- e.g. "admin#991001"
  guard_passcode   text,                  -- e.g. "guard#2024"
  created_at       timestamptz default now()
);

-- 2. GUESTS
create table p_guests (
  id         uuid primary key default gen_random_uuid(),
  event_id   uuid references p_events(id) on delete cascade,
  name       text not null,
  phone      text not null,           -- no +, e.g. 201039048775
  email      text,                    -- optional, required for bulk email sends
  zone       text,                    -- blue | red | green  (optional)
  status     text default 'invited',  -- invited | confirmed | declined | checked_in
  created_at timestamptz default now(),
  unique(event_id, phone)
);

-- 3. TICKETS
create table p_tickets (
  id           uuid primary key default gen_random_uuid(),
  guest_id     uuid references p_guests(id) on delete cascade,
  event_id     uuid references p_events(id) on delete cascade,
  token        text unique not null,  -- UUID stored inside the QR code image
  qr_image_url text,                  -- public URL from Supabase Storage bucket "tickets"
  sent_at      timestamptz,
  created_at   timestamptz default now(),
  unique(event_id, guest_id)          -- one ticket per guest per event
);

-- 4. SCAN LOGS
create table p_scan_logs (
  id          uuid primary key default gen_random_uuid(),
  ticket_id   uuid references p_tickets(id) on delete cascade,  -- nullable for manual ops
  guest_id    uuid references p_guests(id) on delete cascade,   -- denormalised for fast lookup
  gate_number int  default 1,
  action      text not null,          -- checked_in | checked_out
  scanned_at  timestamptz default now()
);

-- 5. WHATSAPP MESSAGE LOG (legacy — Green API only, superseded by p_message_log below)
create table p_wa_messages (
  id           uuid primary key default gen_random_uuid(),
  phone        text not null,
  message_type text,                  -- invitation | ticket | reminder
  status       text default 'sent',
  sent_at      timestamptz default now()
);

-- 6. MESSAGE DELIVERY LOG (WhatsApp Cloud API + email, tracked per guest per event)
create table p_message_log (
  id                   uuid primary key default gen_random_uuid(),
  event_id             uuid references p_events(id) on delete cascade,
  guest_id             uuid references p_guests(id) on delete cascade,
  channel              text not null,                    -- whatsapp | email
  message_type         text not null,                    -- invitation | reminder | ticket | bulk | custom
  recipient            text not null,                     -- phone or email at time of send
  provider_message_id  text,                               -- WA Cloud wamid.xxx OR Resend email id
  status               text not null default 'queued',    -- sent|delivered|read|failed|bounced|complained
  error_detail         text,
  sent_at              timestamptz,
  delivered_at         timestamptz,
  read_at              timestamptz,
  failed_at            timestamptz,
  created_at           timestamptz default now(),
  updated_at           timestamptz default now()
);
create index idx_message_log_event_id           on p_message_log(event_id);
create index idx_message_log_guest_id            on p_message_log(guest_id);
create index idx_message_log_provider_message_id on p_message_log(provider_message_id);

-- ============================================================
-- ROW LEVEL SECURITY
-- The backend uses the service_role key exclusively, which always
-- bypasses RLS regardless of policies. RLS is enabled here with
-- ZERO policies on purpose — this is the strictest possible lockdown
-- for anon/authenticated (they get no access at all) while leaving
-- the backend completely unaffected. Insurance against any future
-- accidental client-side Supabase exposure, not a functional need.
-- ============================================================
alter table p_events      enable row level security;
alter table p_guests      enable row level security;
alter table p_tickets     enable row level security;
alter table p_scan_logs   enable row level security;
alter table p_wa_messages enable row level security;
alter table p_message_log enable row level security;

-- ============================================================
-- MIGRATIONS  (run these if upgrading an existing database)
-- ============================================================
-- alter table p_events      add column if not exists slug             text unique;
-- alter table p_events      add column if not exists manager_passcode text;
-- alter table p_events      add column if not exists guard_passcode   text;
-- alter table p_scan_logs   add column if not exists guest_id         uuid references p_guests(id) on delete cascade;

-- ── Admin redesign: email field + delivery tracking (run this block now) ──
alter table p_guests add column if not exists email text;

create table if not exists p_message_log (
  id                   uuid primary key default gen_random_uuid(),
  event_id             uuid references p_events(id) on delete cascade,
  guest_id             uuid references p_guests(id) on delete cascade,
  channel              text not null,
  message_type         text not null,
  recipient            text not null,
  provider_message_id  text,
  status               text not null default 'queued',
  error_detail         text,
  sent_at              timestamptz,
  delivered_at         timestamptz,
  read_at              timestamptz,
  failed_at            timestamptz,
  created_at           timestamptz default now(),
  updated_at           timestamptz default now()
);
create index if not exists idx_message_log_event_id           on p_message_log(event_id);
create index if not exists idx_message_log_guest_id            on p_message_log(guest_id);
create index if not exists idx_message_log_provider_message_id on p_message_log(provider_message_id);
alter table p_message_log disable row level security;

-- ============================================================
-- STORAGE BUCKET  (do this in the Supabase Dashboard)
-- Dashboard → Storage → New bucket
--   Name   : tickets
--   Public : ON  (toggle on)
-- ============================================================
