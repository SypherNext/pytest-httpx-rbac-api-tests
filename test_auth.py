"""
Login, JWT issuance, and the two distinct auth-failure status codes this
app uses: 401 when there's no token at all, 403 when a token exists but
doesn't verify.
"""
import asyncio

import pytest


def test_login_with_valid_credentials_returns_a_token_and_user(api_client):
    response = api_client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"token", "user"}
    assert isinstance(body["token"], str) and len(body["token"]) > 20
    assert body["user"]["role"] == "Administrator"
    assert set(body["user"].keys()) == {"id", "username", "email", "role", "full_name"}


def test_login_as_each_role_reports_the_correct_role(login_as):
    for role in ("Administrator", "Doctor", "Nurse", "Patient"):
        session = login_as(role)
        assert session["user"]["role"] == role


def test_rejects_requests_with_no_token_at_all(api_client):
    response = api_client.get("/api/appointments")

    assert response.status_code == 401
    assert response.json()["error"] == "Access token required"


def test_rejects_requests_with_a_garbage_token(api_client):
    response = api_client.get(
        "/api/appointments", headers={"Authorization": "Bearer not-a-real-token"}
    )

    assert response.status_code == 403
    assert response.json()["error"] == "Invalid or expired token"


def test_a_valid_token_reaches_a_protected_endpoint(login_as, api_client):
    doctor = login_as("Doctor")
    response = api_client.get("/api/appointments", headers=doctor["headers"])
    assert response.status_code == 200


async def test_several_role_lookups_run_concurrently(async_api_client):
    login = await async_api_client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    )
    headers = {"Authorization": f"Bearer {login.json()['token']}"}

    responses = await asyncio.gather(
        async_api_client.get("/api/users/role/Doctor", headers=headers),
        async_api_client.get("/api/users/role/Nurse", headers=headers),
        async_api_client.get("/api/users/role/Patient", headers=headers),
        async_api_client.get("/api/users/role/Administrator", headers=headers),
    )

    # Assert on shape, not exact totals: this is a shared dev database (see
    # test_database.py's isolation notes), so counts can grow as other test
    # runs register new users. The seed script guarantees these minimums.
    assert all(r.status_code == 200 for r in responses)
    assert len(responses[0].json()) >= 8  # at least the 8 seeded doctors
    assert len(responses[1].json()) >= 7  # at least the 7 seeded nurses
    assert len(responses[2].json()) >= 15  # at least the 15 seeded patients
    assert len(responses[3].json()) >= 1  # at least the default admin
