"""
Negative and edge-case tests: what the API actually does when something is
wrong, confirmed against the real app rather than assumed.
"""
from helpers import unique_username


def test_missing_token_gets_401_invalid_token_gets_403(api_client):
    no_token = api_client.get("/api/appointments")
    assert no_token.status_code == 401
    assert no_token.json()["error"] == "Access token required"

    bad_token = api_client.get(
        "/api/appointments", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert bad_token.status_code == 403
    assert bad_token.json()["error"] == "Invalid or expired token"


def test_wrong_password_gets_401_with_a_generic_message(api_client):
    response = api_client.post(
        "/api/auth/login", json={"username": "admin", "password": "wrong-password"}
    )
    assert response.status_code == 401
    assert response.json()["error"] == "Invalid credentials"


def test_nonexistent_username_gets_the_same_generic_message(api_client):
    """The message doesn't distinguish "unknown username" from "wrong
    password" -- a deliberate security property against username
    enumeration, worth testing for rather than around.
    """
    response = api_client.post(
        "/api/auth/login",
        json={"username": "definitely-not-a-real-user", "password": "anything"},
    )
    assert response.status_code == 401
    assert response.json()["error"] == "Invalid credentials"


def test_empty_login_body_is_a_credentials_failure_not_a_validation_failure(api_client):
    response = api_client.post("/api/auth/login", json={})
    assert response.status_code == 401
    assert response.json()["error"] == "Invalid credentials"


def test_registration_reports_every_validation_failure(api_client):
    response = api_client.post(
        "/api/auth/register",
        json={
            "username": "ab",
            "email": "not-an-email",
            "password": "123",
            "role": "SuperAdmin",
        },
    )

    assert response.status_code == 400
    errors_by_field = {e["path"]: e["msg"] for e in response.json()["errors"]}
    assert errors_by_field["username"] == "Username must be at least 3 characters"
    assert errors_by_field["email"] == "Invalid email address"
    assert errors_by_field["password"] == "Password must be at least 6 characters"
    assert errors_by_field["role"] == "Invalid role"


def test_duplicate_username_on_register_gets_409(api_client):
    response = api_client.post(
        "/api/auth/register",
        json={
            "username": "admin",  # already exists
            "email": "someone-new@example.com",
            "password": "password123",
            "role": "Patient",
            "full_name": "Someone New",
        },
    )
    assert response.status_code == 409


def test_a_genuinely_unique_registration_succeeds(api_client):
    username = unique_username("negtest")
    response = api_client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "password123",
            "role": "Patient",
            "full_name": "Negative Test Patient",
        },
    )
    assert response.status_code == 201
    assert "userId" in response.json()


def test_non_numeric_id_is_not_found_not_bad_request(login_as, api_client):
    admin = login_as("Administrator")
    response = api_client.get(
        "/api/appointments/not-a-number", headers=admin["headers"]
    )
    assert response.status_code == 404


def test_get_nonexistent_appointment_is_404(login_as, api_client):
    admin = login_as("Administrator")
    response = api_client.get("/api/appointments/999999", headers=admin["headers"])
    assert response.status_code == 404


def test_get_nonexistent_medical_record_is_404(login_as, api_client):
    doctor = login_as("Doctor")
    response = api_client.get(
        "/api/medical-records/999999", headers=doctor["headers"]
    )
    assert response.status_code == 404
