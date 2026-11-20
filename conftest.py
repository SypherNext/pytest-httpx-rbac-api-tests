"""
Shared pytest fixtures for the rbac-healthcare-system spec-driven test suite.

Everything here knows HOW to do something generic (log in, look up a seeded
user, query the database, fetch the spec) without knowing WHAT any specific
test is checking. Test files lean on these by naming them as parameters --
no import required at the call site, pytest resolves fixtures by name.
"""
from __future__ import annotations

import os
import sqlite3

import httpx
import pytest

from helpers import fetch_openapi_spec

BASE_URL = os.environ.get("RBAC_BASE_URL", "http://localhost:5000")

# Every seeded account except the default admin uses pass@123.
CREDENTIALS = {
    "Administrator": ("admin", "admin123"),
    "Doctor": ("doctor1", "pass@123"),
    "Nurse": ("nurse1", "pass@123"),
    "Patient": ("patient1", "pass@123"),
}

# The real, running backend's SQLite file. This test project is a genuinely
# separate Python process talking to the app over HTTP -- there's no shared
# memory with the Node process, only a shared filesystem. RBAC_DB_PATH lets
# CI or another machine point somewhere else without editing this file.
DB_PATH = os.environ.get(
    "RBAC_DB_PATH",
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "rbac-healthcare-system",
        "backend",
        "database",
        "rbac.db",
    ),
)


@pytest.fixture
def api_client():
    """A single reused sync httpx.Client, pointed at the real running backend."""
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        yield client


@pytest.fixture
async def async_api_client():
    """Async counterpart of api_client, for tests that need concurrent requests."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        yield client


@pytest.fixture
def login_as(api_client):
    """A fixture that returns a function: login_as("Doctor") -> session dict.

    A plain fixture can't take an argument, so this returns a callable
    instead -- the test decides which role to log in as, pytest still
    resolves api_client as this fixture's own dependency automatically.
    """

    def _login(role: str) -> dict:
        username, password = CREDENTIALS[role]
        response = api_client.post(
            "/api/auth/login", json={"username": username, "password": password}
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Login failed for {role}: {response.status_code} {response.text}"
            )

        body = response.json()
        return {
            "role": role,
            "token": body["token"],
            "user_id": body["user"]["id"],
            "user": body["user"],
            "headers": {"Authorization": f"Bearer {body['token']}"},
        }

    return _login


@pytest.fixture(scope="session")
def openapi_spec():
    """The real OpenAPI spec, fetched once per test run and reused everywhere.

    It doesn't change mid-suite, so there's no reason to re-fetch and
    re-parse it before every single test.
    """
    return fetch_openapi_spec(BASE_URL)


@pytest.fixture
def get_first_user_with_role(login_as, api_client):
    """Look up a real seeded user by role instead of hardcoding an ID.

    SQLite's AUTOINCREMENT never reuses IDs, even after npm run seed deletes
    and reinserts every non-admin user -- so a hardcoded ID like
    patient_id: 20 is only correct until the next reseed. Looking the user
    up by role is stable across reseeds; the literal ID is not.
    """

    def _get(role: str) -> dict:
        admin = login_as("Administrator")
        response = api_client.get(f"/api/users/role/{role}", headers=admin["headers"])
        users = response.json()
        if not users:
            raise RuntimeError(f"No seeded users found with role {role}")
        return users[0]

    return _get


@pytest.fixture
def temporary_appointment(login_as, get_first_user_with_role, api_client):
    """Create an appointment for a test, then delete it once the test is done."""
    admin = login_as("Administrator")
    patient = get_first_user_with_role("Patient")
    doctor = get_first_user_with_role("Doctor")

    created = api_client.post(
        "/api/appointments",
        headers=admin["headers"],
        json={
            "patient_id": patient["id"],
            "doctor_id": doctor["id"],
            "appointment_date": "2026-10-01T09:00:00",
            "reason": "temporary, cleaned up after the test",
        },
    )
    appointment_id = created.json()["appointmentId"]

    yield appointment_id

    api_client.delete(f"/api/appointments/{appointment_id}", headers=admin["headers"])


@pytest.fixture
def db_query():
    """Read-only direct SQLite access to the backend's real database file.

    Used to verify a write actually persisted at the storage layer, not just
    that the API's own GET handler reports it did -- the two could share a
    bug and agree with each other incorrectly.
    """

    def _query_one(sql: str, params: tuple = ()):
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    return _query_one


@pytest.fixture
def db_query_all():
    """Same as db_query, but returns every matching row instead of just one."""

    def _query_all(sql: str, params: tuple = ()):
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    return _query_all
