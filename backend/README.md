# MB Associates Solar Backend & Staff Operations Portal

Production-ready backend for the MB Associates solar advisory website built with **FastAPI**, **Uvicorn**, **Supabase PostgreSQL** (using `psycopg` v3 async connection pool), and **Supabase Auth**.

---

## 1. Architecture & Business Workflow Overview

MB Associates is an end-to-end solar project assistance and coordination partner. Every customer enquiry is received directly by MB Associates staff for in-house technical feasibility review, documentation assistance, and offline coordination with nearby verified vendors.

- **Customer Journey**: Public visitors can browse services, understand the 6-step coordination process, use the client-side Solar Feasibility Estimator, and submit an assistance or site visit request via `POST /api/enquiries`.
- **Database Idempotency**: An identical retry returns the original reference code (`MBA-YYYYMM-XXXXX`). A submission with the same contact and PIN but conflicting request details returns `409 Conflict`.
- **Private Staff Operations Queue**: Authorized coordinators sign in with Supabase Auth to view the private queue, search enquiries by reference or customer name, filter by status (`New`, `Contacted`, `In Progress`, `Closed`), update statuses, and log internal coordination notes.
- **Strict Data Privacy**: Enquiries, staff membership, and notes are stored in private PostgreSQL tables protected by Row Level Security (RLS) with all public PostgREST permissions revoked. FastAPI connects directly via PostgreSQL connection pool.

---

## 2. Directory Structure

```
associate/
  about.html
  contact.html
  enquiry.html
  enquiry-confirmation.html
  how-it-works.html
  index.html
  installation.html
  mb-associates-logo.png
  services.html
  solar-calculator.html
  solutions.html
  subsidy-finance.html
  .gitignore
  backend/
    requirements.txt
    .env.example
    README.md
    app/
      __init__.py
      main.py               # FastAPI application, route whitelisting, lifespan
      config.py             # Pydantic Settings loaded from .env
      db.py                 # psycopg async connection pool & get_db_connection
      schemas.py            # Pydantic validation schemas
      auth.py               # Supabase Auth, sessions, CSRF & rate limiting
      routers/
        __init__.py
        enquiries.py        # POST /api/enquiries with idempotency
        staff.py            # Staff login, queue UI, and operations API
      templates/
        staff_login.html    # Staff sign in template
        staff_enquiries.html# Staff queue dashboard template
      static/
        enquiry.js          # Customer form submission script
        confirmation.js     # Confirmation page reference populator
        staff.js            # Staff queue management script
    migrations/
      001_initial.sql       # Versioned schema migration & RLS policies
    tests/
      test_enquiries.py     # Enquiry submission, validation & idempotency tests
      test_staff.py         # Staff auth, queue, status update & notes tests
```

---

## 3. Windows PowerShell Setup & Execution Guide

Follow these exact commands in **Windows PowerShell** to configure, run, and test the project:

### Step 3.1: Navigate to Workspace and Create Virtual Environment

```powershell
# Open Windows PowerShell and navigate to the project directory
cd D:\associate\backend

# Create a Python 3.13 virtual environment
python -m venv venv

# Activate the virtual environment
.\venv\Scripts\Activate.ps1
```

> **Note**: If script execution is restricted on your machine, temporarily enable it for your session:
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> .\venv\Scripts\Activate.ps1
> ```

### Step 3.2: Install Required Packages

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3.3: Configure Environment Variables

Create `D:\associate\backend\.env` from the template:

```powershell
Copy-Item .env.example .env
```

Edit `backend/.env` with your actual Supabase project credentials:

```env
# Supabase PostgreSQL Database Connection String (Direct or Transaction Pooler)
# Found in: Supabase Dashboard -> Project Settings -> Database -> Connection String (URI)
DATABASE_URL=postgresql://postgres:[YOUR-DB-PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:6543/postgres?sslmode=require

# Supabase Project URL and Public Anon Key
# Found in: Supabase Dashboard -> Project Settings -> API
SUPABASE_URL=https://[YOUR-PROJECT-REF].supabase.co
SUPABASE_PUBLISHABLE_KEY=[YOUR-SUPABASE-ANON-KEY]

# Application Origin & Security Secrets
APP_ORIGIN=http://localhost:8000
SESSION_SECRET=a_very_strong_random_secret_string_minimum_32_characters_long
ENVIRONMENT=development
```

### Step 3.4: Apply the PostgreSQL Schema Migration

#### Option A: Via Supabase Web Dashboard (Recommended)
1. Open your Supabase Dashboard: `https://supabase.com/dashboard/project/[YOUR-PROJECT-REF]`
2. Go to the **SQL Editor** on the left menu.
3. Open `D:\associate\backend\migrations\001_initial.sql`, copy its entire content, and paste it into the SQL Editor.
4. Click **Run**. This creates the `enquiries`, `staff_members`, and `staff_notes` tables and configures RLS.

#### Option B: Via `psql` Command Line
```powershell
# If PostgreSQL client tools are installed:
psql "$env:DATABASE_URL" -f D:\associate\backend\migrations\001_initial.sql
```

### Step 3.5: Provision the First Staff Member

MB Associates staff accounts use Supabase Auth tied to the `staff_members` table.

1. In Supabase Dashboard, go to **Authentication** -> **Users** -> **Add User** -> **Create User**.
   - Email: `coordinator@mbassociates.internal` (or your staff email)
   - Password: `[Choose a strong password]`
   - Auto Confirm User: Checked
2. Copy the generated **User UID** (UUID).
3. In Supabase **SQL Editor**, run this query to authorize the user in `staff_members`:
   ```sql
   INSERT INTO public.staff_members (auth_user_id, email, name, role)
   VALUES (
       'PASTE-USER-UID-HERE',
       'coordinator@mbassociates.internal',
       'Senior Solar Project Coordinator',
       'coordinator'
   );
   ```

### Step 3.6: Run the FastAPI Development Server

```powershell
cd D:\associate\backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Once running, access:
- **Public Solar Website**: [http://localhost:8000/](http://localhost:8000/)
- **Solar Feasibility Calculator**: [http://localhost:8000/solar-calculator.html](http://localhost:8000/solar-calculator.html)
- **Assistance Request Form**: [http://localhost:8000/enquiry.html](http://localhost:8000/enquiry.html)
- **Private Staff Login**: [http://localhost:8000/staff/login](http://localhost:8000/staff/login)
- **Staff Operations Queue**: [http://localhost:8000/staff/enquiries](http://localhost:8000/staff/enquiries)
- **API Health Check**: [http://localhost:8000/health](http://localhost:8000/health)
- **Interactive OpenAPI Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

### Step 3.7: Execute the Test Suite

Run all unit and integration tests:

```powershell
cd D:\associate\backend
pytest -v
```

---

## 4. Security & Least-Privilege Role Setup

To protect your Supabase database in production:

1. **Row Level Security (RLS)** is enabled on all tables:
   ```sql
   REVOKE ALL ON public.enquiries FROM anon, authenticated;
   REVOKE ALL ON public.staff_members FROM anon, authenticated;
   REVOKE ALL ON public.staff_notes FROM anon, authenticated;
   ```
2. **Dedicated FastAPI Runtime Role**:
   Run the following SQL in Supabase to create a least-privilege role for the backend rather than using the superuser `postgres`:
   ```sql
   CREATE ROLE mb_fastapi_role WITH LOGIN PASSWORD 'YOUR_STRONG_PASSWORD_HERE';
   GRANT CONNECT ON DATABASE postgres TO mb_fastapi_role;
   GRANT USAGE ON SCHEMA public TO mb_fastapi_role;
   GRANT SELECT, INSERT, UPDATE ON TABLE public.enquiries TO mb_fastapi_role;
   GRANT SELECT, INSERT, UPDATE ON TABLE public.staff_members TO mb_fastapi_role;
   GRANT SELECT, INSERT, UPDATE ON TABLE public.staff_notes TO mb_fastapi_role;
   ```
   Then set `DATABASE_URL` in `backend/.env` with `mb_fastapi_role`.

---

## 5. Solar Calculator Verification

The calculator located at `solar-calculator.html` operates strictly client-side using validated parameters from `mb-solar-calculator (localEngine.ts)`:
- **Test Case**: Andhra Pradesh, Residential, ₹3,500 monthly bill.
- **Expected Results**:
  - Capacity: **3.5 kWp** (Ideal ~3.6 kWp rounded to nearest 0.5 kWp)
  - Annual Generation: **5,748.8 kWh/year** (`3.5 kWp * 4.5 kWh/kW/day * 365 days`)
  - Usable Rooftop Footprint: **~350 sq. ft** (`3.5 * 100 sq.ft/kWp`)
- The "Request Solar Project Assistance" button links directly to `enquiry.html` with pre-filled parameters.
