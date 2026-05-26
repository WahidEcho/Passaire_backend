-- ============================================================
-- PASSAIRE — FULL SCHEMA  (copy-paste into Supabase SQL Editor)
-- ============================================================

-- 1. EVENTS
create table p_events (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  date       date not null,
  venue      text,
  gate_count int  default 1,
  created_at timestamptz default now()
);

-- 2. GUESTS
create table p_guests (
  id         uuid primary key default gen_random_uuid(),
  event_id   uuid references p_events(id) on delete cascade,
  name       text not null,
  phone      text not null,           -- no +, e.g. 201039048775
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
  ticket_id   uuid references p_tickets(id) on delete cascade,
  gate_number int  default 1,
  action      text not null,          -- checked_in | checked_out
  scanned_at  timestamptz default now()
);

-- 5. WHATSAPP MESSAGE LOG
create table p_wa_messages (
  id           uuid primary key default gen_random_uuid(),
  phone        text not null,
  message_type text,                  -- invitation | ticket | reminder
  status       text default 'sent',
  sent_at      timestamptz default now()
);

-- ============================================================
-- DISABLE ROW LEVEL SECURITY
-- (backend uses service_role key which bypasses RLS anyway,
--  but disabling keeps things explicit)
-- ============================================================
alter table p_events      disable row level security;
alter table p_guests      disable row level security;
alter table p_tickets     disable row level security;
alter table p_scan_logs   disable row level security;
alter table p_wa_messages disable row level security;

-- ============================================================
-- STORAGE BUCKET  (do this in the Supabase Dashboard)
-- Dashboard → Storage → New bucket
--   Name   : tickets
--   Public : ON  (toggle on)
-- ============================================================
