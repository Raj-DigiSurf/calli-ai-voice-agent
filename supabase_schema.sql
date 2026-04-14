-- ============================================================
-- Calli AI Voice Agent — Supabase Schema
-- Run this in your Supabase project → SQL Editor → New query
-- ============================================================

-- ── Businesses ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS businesses (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name            TEXT NOT NULL,
    slug            TEXT UNIQUE NOT NULL,          -- e.g. "dalliance-hair"
    phone_number    TEXT,                          -- Twilio number Calli answers
    transfer_number TEXT,                          -- "speak to a real person" target
    booking_system  TEXT DEFAULT 'none',           -- kitomba | mindbody | cliniko | none
    system_url      TEXT,                          -- Playwright target URL
    timezone        TEXT DEFAULT 'Australia/Sydney',
    booking_confirm_url TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ── Business hours ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS business_hours (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    business_id     TEXT REFERENCES businesses(id) ON DELETE CASCADE,
    day_of_week     INT NOT NULL,   -- 0=Mon … 6=Sun
    open_time       TEXT,           -- HH:MM, null = closed
    close_time      TEXT,
    UNIQUE(business_id, day_of_week)
);

-- ── Staff ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS staff (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    business_id     TEXT REFERENCES businesses(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    active          BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ── Services ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS services (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    business_id     TEXT REFERENCES businesses(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    duration_mins   INT NOT NULL DEFAULT 60,
    price_min       INT,            -- in AUD cents
    price_max       INT,
    deposit_amount  INT DEFAULT 5000,   -- $50.00 in cents
    active          BOOLEAN DEFAULT true
);

-- ── Cancellation policy ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cancellation_policies (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    business_id     TEXT REFERENCES businesses(id) ON DELETE CASCADE UNIQUE,
    hours_notice    INT DEFAULT 24,    -- minimum hours notice required
    fee_amount      INT DEFAULT 0      -- fee in AUD cents (0 = no fee)
);

-- ── FAQ / knowledge base ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS faq (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    business_id     TEXT REFERENCES businesses(id) ON DELETE CASCADE,
    question        TEXT NOT NULL,
    answer          TEXT NOT NULL
);

-- ── Customers ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS customers (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    business_id     TEXT REFERENCES businesses(id) ON DELETE CASCADE,
    phone           TEXT NOT NULL,
    name            TEXT,
    email           TEXT,
    notes           TEXT,   -- e.g. "allergic to ammonia", "prefers Sarah"
    created_at      TIMESTAMPTZ DEFAULT now(),
    last_seen_at    TIMESTAMPTZ DEFAULT now(),
    UNIQUE(business_id, phone)
);

-- ── Bookings ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bookings (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    business_id     TEXT REFERENCES businesses(id) ON DELETE CASCADE,
    service         TEXT NOT NULL,
    staff_name      TEXT DEFAULT '(anyone)',
    date            TEXT NOT NULL,   -- YYYY-MM-DD
    time            TEXT NOT NULL,   -- HH:MM
    duration_mins   INT DEFAULT 60,
    customer_phone  TEXT NOT NULL,
    customer_name   TEXT,
    status          TEXT DEFAULT 'confirmed',  -- confirmed|cancelled|completed|no_show
    source          TEXT DEFAULT 'voice',      -- voice|web|walk_in
    deposit_paid    BOOLEAN DEFAULT false,
    cancelled_at    TIMESTAMPTZ,
    cancelled_reason TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_bookings_date        ON bookings(business_id, date);
CREATE INDEX IF NOT EXISTS idx_bookings_phone       ON bookings(business_id, customer_phone);
CREATE INDEX IF NOT EXISTS idx_bookings_status      ON bookings(business_id, status);

-- ── Waitlist ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS waitlist (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    business_id     TEXT REFERENCES businesses(id) ON DELETE CASCADE,
    customer_phone  TEXT NOT NULL,
    customer_name   TEXT,
    service         TEXT,
    preferred_date  TEXT,    -- YYYY-MM-DD
    time_preference TEXT DEFAULT 'any',   -- any | morning | afternoon
    status          TEXT DEFAULT 'waiting',   -- waiting | notified | booked
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ── Callbacks ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS callbacks (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    business_id     TEXT REFERENCES businesses(id) ON DELETE CASCADE,
    customer_phone  TEXT NOT NULL,
    customer_name   TEXT,
    reason          TEXT,
    status          TEXT DEFAULT 'pending',   -- pending | called | resolved
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ── Seed: default Dalliance business record ───────────────────────────────────
INSERT INTO businesses (id, name, slug, booking_system, timezone, booking_confirm_url)
VALUES (
    'default',
    'Dalliance Hair Studio',
    'dalliance-hair',
    'kitomba',
    'Australia/Sydney',
    'https://kitomba.com/bookings/dalliancehair'
) ON CONFLICT (id) DO NOTHING;
