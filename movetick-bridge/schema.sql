-- ============================================================
-- PASSAIRE EVENT SCHEMA
-- Run this in Supabase SQL Editor
-- ============================================================

-- NOTE: Tables are prefixed with p_ to avoid conflicts with the existing
-- platform schema (which already uses "events" and "tickets" table names).

-- EVENTS
create table if not exists p_events (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  date       date not null,
  venue      text,
  gate_count int  default 1,
  created_at timestamptz default now()
);

-- GUESTS
create table if not exists p_guests (
  id         uuid primary key default gen_random_uuid(),
  event_id   uuid references p_events(id) on delete cascade,
  name       text not null,
  phone      text not null,            -- international format, NO +, e.g. 201039048775
  status     text default 'invited',   -- invited | confirmed | declined | checked_in
  created_at timestamptz default now(),
  unique(event_id, phone)
);

-- TICKETS
create table if not exists p_tickets (
  id           uuid primary key default gen_random_uuid(),
  guest_id     uuid references p_guests(id) on delete cascade,
  event_id     uuid references p_events(id) on delete cascade,
  token        text unique not null,   -- UUID encoded in the QR image
  qr_image_url text,                   -- public URL from Supabase Storage bucket "tickets"
  sent_at      timestamptz,
  created_at   timestamptz default now()
);

-- SCAN LOGS
create table if not exists p_scan_logs (
  id          uuid primary key default gen_random_uuid(),
  ticket_id   uuid references p_tickets(id) on delete cascade,
  gate_number int  default 1,
  action      text not null,           -- checked_in | checked_out
  scanned_at  timestamptz default now()
);

-- WHATSAPP MESSAGE LOG
create table if not exists p_wa_messages (
  id           uuid primary key default gen_random_uuid(),
  phone        text not null,
  message_type text,                   -- invitation | ticket | reminder | agenda
  status       text default 'sent',
  sent_at      timestamptz default now()
);

-- ============================================================
-- STORAGE BUCKET
-- Dashboard → Storage → New bucket → name: "tickets" → Public: ON
-- ============================================================

-- ============================================================
-- DISABLE RLS (service_role key bypasses RLS, but disabling
-- avoids confusion if you ever switch to anon key)
-- ============================================================
alter table p_events      disable row level security;
alter table p_guests      disable row level security;
alter table p_tickets     disable row level security;
alter table p_scan_logs   disable row level security;
alter table p_wa_messages disable row level security;
