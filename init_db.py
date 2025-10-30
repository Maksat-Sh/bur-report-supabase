# SQL to create tables in Supabase
print("""CREATE TABLE IF NOT EXISTS public.reports (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  date_time timestamptz,
  location text,
  rig_number text,
  meterage numeric,
  pogon numeric,
  operation text,
  note text,
  operator_name text,
  created_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.users (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  username text UNIQUE,
  password_hash text NOT NULL,
  role text,
  full_name text,
  location text,
  rig_number text,
  created_at timestamptz DEFAULT now()
);
""")