"""
API security tests: two real defenses confirmed working, and one real,
unfixed gap documented as it actually behaves today.
"""
import pytest

from helpers import decode_jwt_payload, forge_tampered_token, unique_username


@pytest.mark.security
def test_jwt_payload_is_readable_without_the_servers_secret(login_as):
    """JWTs are signed, not encrypted -- the payload is just base64url, no
    secret required to read it. Not a vulnerability by itself (nothing
    sensitive like a password lives in the token), but worth confirming.
    """
    patient = login_as("Patient")
    payload = decode_jwt_payload(patient["token"])

    assert payload["username"] == "patient1"
    assert payload["role"] == "Patient"


@pytest.mark.security
def test_rejects_a_token_with_a_tampered_payload_even_if_the_shape_looks_valid(
    login_as, api_client
):
    patient = login_as("Patient")
    forged_token = forge_tampered_token(patient["token"], role="Administrator")

    response = api_client.get(
        "/api/users", headers={"Authorization": f"Bearer {forged_token}"}
    )

    assert response.status_code == 403
    assert response.json()["error"] == "Invalid or expired token"


@pytest.mark.security
def test_does_not_let_a_sql_injection_payload_bypass_login(api_client):
    response = api_client.post(
        "/api/auth/login",
        json={"username": "admin' OR '1'='1", "password": "anything"},
    )
    assert response.status_code == 401
    assert response.json()["error"] == "Invalid credentials"


@pytest.mark.security
def test_sql_injection_in_username_at_registration_is_treated_as_plain_data(api_client):
    # A unique suffix keeps this repeatable across runs against the same
    # shared, persistent dev database -- a fixed literal username would
    # 409 on every run after the first (see conftest.py's notes on test
    # isolation against a database with no per-run reset).
    username = f"'; DROP TABLE users; -- {unique_username()}"
    response = api_client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{unique_username('injection-test')}@example.com",
            "password": "password123",
            "role": "Patient",
            "full_name": "Injection Test",
        },
    )
    # Either it's rejected by validation, or created as a literal, harmless
    # username -- either way the users table must still exist afterward.
    assert response.status_code in (201, 400)

    login = api_client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert login.status_code == 200  # the table wasn't dropped


@pytest.mark.security
def test_lets_a_patient_create_an_appointment_under_a_different_patient_id(
    login_as, get_first_user_with_role, api_client
):
    """A real, verified gap: POST /api/appointments takes patient_id
    straight from the request body and never checks it against the
    identity of whoever is actually authenticated.
    """
    patient1 = login_as("Patient")
    someone_else = get_first_user_with_role("Patient")
    doctor = get_first_user_with_role("Doctor")

    response = api_client.post(
        "/api/appointments",
        headers=patient1["headers"],
        json={
            "patient_id": someone_else["id"],
            "doctor_id": doctor["id"],
            "appointment_date": "2026-09-05T10:00:00",
            "reason": "tampered",
        },
    )

    # Documenting the app's real, current behavior: this succeeds.
    assert response.status_code == 201
    assert "appointmentId" in response.json()
