-- SQL for Supabase (run in SQL editor)
CREATE TABLE IF NOT EXISTS public.users (
  id bigserial primary key,
  username text UNIQUE NOT NULL,
  password_hash text NOT NULL,
  full_name text,
  role text,
  location text,
  unit text,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.reports (
  id bigserial primary key,
  date_time timestamptz,
  location text,
  rig_number text,
  meterage numeric,
  pogon numeric,
  operation text,
  operator_name text,
  note text,
  created_at timestamptz DEFAULT now()
);
