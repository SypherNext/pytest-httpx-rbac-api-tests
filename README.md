# pytest-httpx-rbac-api-tests

A real, working pytest + httpx test suite for `rbac-healthcare-system`, a
small Express + SQLite RBAC healthcare API. This is the reference
implementation for the "API Testing using Python" course: a genuinely
black-box test project that sends real HTTP requests to a real, running
backend and never imports a single line of that backend's own code.

Nothing here is a toy example. Every test in this repo runs against the
real app and was verified passing against it before being committed.

## What's covered

- Login, JWT issuance, and the two distinct auth-failure codes this app
  uses (`401` with no token, `403` with an invalid one)
- Full CRUD lifecycles for appointments and medical records, each with a
  read-after-write check that proves a write actually persisted
- The real, verified 4-role permission matrix (Administrator / Doctor /
  Nurse / Patient), including two places where real enforcement diverges
  from what you'd expect from the docs
- Negative and edge-case tests: wrong credentials, malformed registration
  payloads, a non-numeric ID, an unvalidated route that fails with a raw
  `500` instead of a clean `400`
- Security tests: JWT payload tampering, SQL-injection resistance, and one
  real, unfixed parameter-tampering gap on appointment creation
- Schema and contract validation: `jsonschema` against the spec's own
  declared request schemas, Pydantic models for responses the spec
  doesn't describe
- Reading the OpenAPI spec directly out of the Swagger UI's generated
  JavaScript (this app has no dedicated `/openapi.json` route) and
  property-based testing against it with Schemathesis
- Direct SQLite verification of writes, alongside the HTTP-level checks
- A capstone suite covering registration and `/api/users` end to end

## Project layout

```
conftest.py                      shared fixtures: api_client, login_as,
                                  get_first_user_with_role, openapi_spec,
                                  db_query, temporary_appointment
helpers.py                       plain functions: fetch_openapi_spec,
                                  list_operations, JWT helpers, etc.
pytest.ini                       project config, markers
requirements.txt
test_auth.py                     login, JWT, async concurrent requests
test_appointments.py             CRUD lifecycle, role-gate behavior
test_medical_records.py          CRUD lifecycle, Doctor-only writes
test_rbac_matrix.py              the full 4-role permission matrix
test_negative.py                 wrong input, confirmed real behavior
test_security.py                 JWT tampering, SQLi, parameter tampering
test_schema_contract.py          jsonschema + Pydantic contract checks
test_database.py                 direct SQLite verification
test_mocking.py                  respx used only on this project's OWN
                                  code, never against the real app
test_smoke.py                    fast critical-path + timing sanity checks
test_schemathesis_contract.py    property-based spec compliance
test_users_capstone.py           full coverage of users + registration
```

## What this is testing

This suite tests
[`rbac-healthcare-system`](https://github.com/codedbyabhishekc/rbac-healthcare-system),
a small Express/SQLite API with JWT auth and 4 roles (Administrator,
Doctor, Nurse, Patient). This repo is a completely separate project from
it -- it only ever talks to the backend over plain HTTP on
`http://localhost:5000`.

## Setup

### 1. Clone and run the backend under test

```bash
git clone https://github.com/codedbyabhishekc/rbac-healthcare-system.git
cd rbac-healthcare-system/backend
npm install
mkdir database
```

Create a `.env` file inside `backend/`:

```
PORT=5000
JWT_SECRET=any-long-random-string-you-want
NODE_ENV=development
```

Start it, then seed it in a second terminal (or stop and restart after
seeding):

```bash
npm start
```

```bash
npm run seed
```

Leave the backend running. Confirm it's up:

```bash
curl http://localhost:5000/health
```

### 2. Set up this project

Clone or copy this repo into a sibling directory (not inside
`rbac-healthcare-system`), then, from inside it:

**Windows (PowerShell or cmd):**

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

**macOS / Linux:**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Run the suite

```bash
pytest
```

Useful variations:

```bash
pytest -v                               # one line per test
pytest -m smoke                         # just the fast critical-path checks
pytest -n auto                          # parallel, across CPU cores
pytest --html=report.html --self-contained-html   # a shareable HTML report
pytest --cov=. --cov-report=term-missing           # coverage of this project's own code
```

## Configuration

Two environment variables, both optional:

| Variable         | Default                                                              | Purpose                                    |
|------------------|-----------------------------------------------------------------------|---------------------------------------------|
| `RBAC_BASE_URL`  | `http://localhost:5000`                                                | Where the backend is running                |
| `RBAC_DB_PATH`   | `../rbac-healthcare-system/backend/database/rbac.db` (sibling folder) | Direct SQLite path for `test_database.py`   |

Set `RBAC_DB_PATH` explicitly if your two projects aren't laid out as
sibling folders.

## A real limitation worth knowing about

This app has one shared SQLite file and no way to reset it between test
runs. Tests in this suite are written to assert on what they create, not
on exact totals, for exactly that reason -- see the comments in
`test_database.py` and `conftest.py`'s `get_first_user_with_role` fixture.
Running this suite will add some test data (new patients, appointments,
medical records) to whatever database you point it at. That's expected
and harmless; just don't point it at a database you care about keeping
pristine.

Property-based testing (`test_schemathesis_contract.py`) intentionally
only generates requests against read-only `GET` endpoints for this
reason -- random fuzzing against write endpoints with an admin token can
land on a real seeded account's ID and modify or delete it, since this
app has no sandboxed test mode. Every write operation has deliberate,
hand-written coverage elsewhere in this suite instead.

## Known, real gaps in the app this suite documents rather than hides

- `POST /api/appointments` has no role gate at all -- any authenticated
  role, including Patient, can create one.
- `POST /api/appointments` also takes `patient_id` straight from the
  request body with no ownership check, so a patient can book an
  appointment under a different patient's ID.
- `POST /api/appointments` has no input validation layer: a request
  missing the required `patient_id` fails at the database with a raw
  `500`, not a clean `400`.
- `GET /api/medical-records` does not scope results for a Nurse -- a
  Nurse sees every record, the same as an Administrator.
- `POST /api/medical-records` accepts a payload missing its own
  spec-required `diagnosis` field; the spec documents it as required,
  the route doesn't enforce it.

These are documented as passing, intentional tests of real behavior, not
disabled or skipped tests waiting to be fixed.

## License

Copyright (C) 2026 SypherNext

This project is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0). You may
use, study and change it. If you share a modified version, or run one as a website or service
that other people use, you must make your full modified source code available under the same
license. See [LICENSE](LICENSE) for the full terms.
