-- ============================================================================
-- Migration: 001_initial.sql
-- Project: MB Associates Solar Backend
-- Target: Supabase PostgreSQL (or standard PostgreSQL 14+)
-- Description:
--   Creates private tables for customer enquiries, staff membership tied to
--   Supabase Auth user UUID, and internal staff notes.
--   Enforces Row Level Security (RLS) to prevent public anonymous or authenticated
--   Supabase client access, keeping all enquiry data and notes private to FastAPI.
-- ============================================================================

-- Enable pgcrypto for gen_random_uuid() if not enabled
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ----------------------------------------------------------------------------
-- 1. Table: enquiries
-- Stores all public customer solar project assistance & site visit enquiries.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.enquiries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reference TEXT UNIQUE NOT NULL,
    idempotency_hash TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    contact_method TEXT NOT NULL CHECK (contact_method IN ('phone', 'whatsapp', 'email')),
    contact_detail TEXT NOT NULL,
    pin_code CHAR(6) NOT NULL,
    property_type TEXT NOT NULL,
    request_type TEXT NOT NULL DEFAULT 'general' CHECK (request_type IN ('general', 'site_visit')),
    assistance TEXT[] NOT NULL DEFAULT '{}',
    roof_area TEXT,
    monthly_bill NUMERIC(12, 2),
    notes TEXT,
    consent BOOLEAN NOT NULL DEFAULT false,
    status TEXT NOT NULL DEFAULT 'New' CHECK (status IN ('New', 'Contacted', 'In Progress', 'Closed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes for enquiries query performance
CREATE INDEX IF NOT EXISTS idx_enquiries_reference ON public.enquiries (reference);
CREATE INDEX IF NOT EXISTS idx_enquiries_idempotency ON public.enquiries (idempotency_hash);
CREATE INDEX IF NOT EXISTS idx_enquiries_status ON public.enquiries (status);
CREATE INDEX IF NOT EXISTS idx_enquiries_created_at ON public.enquiries (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_enquiries_pin_code ON public.enquiries (pin_code);

-- ----------------------------------------------------------------------------
-- 2. Table: staff_members
-- Authorizes specific Supabase Auth users as MB Associates internal staff.
-- Ties the Supabase Auth user UUID (auth.users.id) to staff role.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.staff_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_user_id UUID UNIQUE NOT NULL,
    email TEXT NOT NULL,
    name TEXT,
    role TEXT NOT NULL DEFAULT 'coordinator' CHECK (role IN ('coordinator', 'engineer', 'admin')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_staff_members_auth_user_id ON public.staff_members (auth_user_id);
CREATE INDEX IF NOT EXISTS idx_staff_members_email ON public.staff_members (email);

-- ----------------------------------------------------------------------------
-- 3. Table: staff_notes
-- Internal coordination notes added by staff to specific customer enquiries.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.staff_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    enquiry_id UUID NOT NULL REFERENCES public.enquiries (id) ON DELETE CASCADE,
    staff_id UUID REFERENCES public.staff_members (id) ON DELETE SET NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_staff_notes_enquiry_id ON public.staff_notes (enquiry_id);
CREATE INDEX IF NOT EXISTS idx_staff_notes_created_at ON public.staff_notes (created_at ASC);

-- ----------------------------------------------------------------------------
-- 4. Row Level Security (RLS) & Access Restrictions
-- Completely block direct public access (anon and authenticated) via Supabase
-- PostgREST API. FastAPI connects directly using the PostgreSQL connection string.
-- ----------------------------------------------------------------------------
ALTER TABLE public.enquiries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.staff_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.staff_notes ENABLE ROW LEVEL SECURITY;

-- Revoke all permissions on these tables from anon and authenticated roles
REVOKE ALL ON public.enquiries FROM anon, authenticated;
REVOKE ALL ON public.staff_members FROM anon, authenticated;
REVOKE ALL ON public.staff_notes FROM anon, authenticated;

-- ----------------------------------------------------------------------------
-- 5. Least-Privilege Database Role Guide for FastAPI Runtime
-- In production, rather than using the superuser 'postgres', create a dedicated
-- least-privilege role for the FastAPI service:
--
-- Example SQL to execute in Supabase SQL Editor:
--
-- CREATE ROLE mb_fastapi_role WITH LOGIN PASSWORD 'YOUR_STRONG_PASSWORD_HERE';
-- GRANT CONNECT ON DATABASE postgres TO mb_fastapi_role;
-- GRANT USAGE ON SCHEMA public TO mb_fastapi_role;
-- GRANT SELECT, INSERT, UPDATE ON TABLE public.enquiries TO mb_fastapi_role;
-- GRANT SELECT, INSERT, UPDATE ON TABLE public.staff_members TO mb_fastapi_role;
-- GRANT SELECT, INSERT, UPDATE ON TABLE public.staff_notes TO mb_fastapi_role;
--
-- Then set DATABASE_URL in backend/.env:
-- DATABASE_URL=postgresql://mb_fastapi_role:YOUR_STRONG_PASSWORD_HERE@aws-0-ap-south-1.pooler.supabase.com:6543/postgres?sslmode=require
-- ----------------------------------------------------------------------------
