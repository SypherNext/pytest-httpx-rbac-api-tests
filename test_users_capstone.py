"""
Capstone: a full spec-driven suite for the one area this project has only
ever touched in passing -- registration and /api/users -- applying every
technique from this suite end to end: a spec-derived checklist, a
parametrized RBAC matrix, ownership checks (not just role checks),
jsonschema validation against the spec's own declared schema, CRUD with
read-after-write verification, and negative cases.
"""
import jsonschema
import pytest

from helpers import list_operations, unique_username


def test_users_and_auth_checklist_matches_the_spec(openapi_spec):
    operations = list_operations(openapi_spec)
    relevant = [op for op in operations if "/users" in op["path"] or "/auth" in op["path"]]

    paths = {(op["method"], op["path"]) for op in relevant}
    assert paths == {
        ("POST", "/api/auth/register"),
        ("POST", "/api/auth/login"),
        ("GET", "/api/users"),
        ("GET", "/api/users/{id}"),
        ("PUT", "/api/users/{id}"),
        ("DELETE", "/api/users/{id}"),
        ("GET", "/api/users/role/{role}"),
    }


@pytest.mark.parametrize(
    "role,expected_status",
    [
        pytest.param("Administrator", 200, id="admin-can-list-users"),
        pytest.param("Doctor", 403, id="doctor-forbidden"),
        pytest.param("Nurse", 403, id="nurse-forbidden"),
        pytest.param("Patient", 403, id="patient-forbidden"),
    ],
)
def test_list_all_users_role_gate(login_as, api_client, role, expected_status):
    session = login_as(role)
    response = api_client.get("/api/users", headers=session["headers"])
    assert response.status_code == expected_status


def test_a_user_can_view_their_own_profile(login_as, api_client):
    patient = login_as("Patient")
    response = api_client.get(f"/api/users/{patient['user_id']}", headers=patient["headers"])
    assert response.status_code == 200
    assert response.json()["id"] == patient["user_id"]


def test_a_user_cannot_view_someone_elses_profile(login_as, get_first_user_with_role, api_client):
    patient = login_as("Patient")
    admin = get_first_user_with_role("Administrator")

    response = api_client.get(f"/api/users/{admin['id']}", headers=patient["headers"])
    assert response.status_code == 403


def test_an_administrator_can_view_anyones_profile(login_as, get_first_user_with_role, api_client):
    admin = login_as("Administrator")
    patient = get_first_user_with_role("Patient")

    response = api_client.get(f"/api/users/{patient['id']}", headers=admin["headers"])
    assert response.status_code == 200


def test_a_user_cannot_update_someone_elses_profile(
    login_as, get_first_user_with_role, api_client
):
    patient = login_as("Patient")
    admin = get_first_user_with_role("Administrator")

    response = api_client.put(
        f"/api/users/{admin['id']}", headers=patient["headers"], json={"full_name": "hacked"}
    )
    assert response.status_code == 403


def test_registers_a_new_patient_matching_the_spec_schema(openapi_spec, api_client):
    schema = openapi_spec["paths"]["/api/auth/register"]["post"]["requestBody"][
        "content"
    ]["application/json"]["schema"]
    username = unique_username("capstone_patient")
    payload = {
        "username": username,
        "email": f"{username}@example.com",
        "password": "correct-horse-1",
        "role": "Patient",
        "full_name": "Capstone Test Patient",
    }
    jsonschema.validate(instance=payload, schema=schema)

    response = api_client.post("/api/auth/register", json=payload)
    assert response.status_code == 201
    assert "userId" in response.json()


def test_updates_and_persists_a_profile_change(login_as, api_client):
    patient = login_as("Patient")

    updated = api_client.put(
        f"/api/users/{patient['user_id']}",
        headers=patient["headers"],
        json={"full_name": "Updated Name", "phone": "555-0000", "email": "updated@example.com"},
    )
    assert updated.status_code == 200

    fetched = api_client.get(f"/api/users/{patient['user_id']}", headers=patient["headers"])
    assert fetched.json()["full_name"] == "Updated Name"

    # Restore the seeded account's original profile so this test is
    # repeatable against the same shared, persistent dev database.
    api_client.put(
        f"/api/users/{patient['user_id']}",
        headers=patient["headers"],
        json={
            "full_name": patient["user"]["full_name"],
            "email": patient["user"]["email"],
        },
    )


@pytest.mark.parametrize(
    "role",
    [
        pytest.param("Administrator", id="admin-can-lookup-by-role"),
        pytest.param("Doctor", id="doctor-can-lookup-by-role"),
        pytest.param("Nurse", id="nurse-can-lookup-by-role"),
        pytest.param("Patient", id="patient-can-lookup-by-role"),
    ],
)
def test_get_users_by_role_is_open_to_any_authenticated_role(login_as, api_client, role):
    session = login_as(role)
    response = api_client.get("/api/users/role/Doctor", headers=session["headers"])
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) > 0


def test_rejects_a_request_with_no_token(api_client):
    response = api_client.get("/api/users")
    assert response.status_code == 401


def test_returns_404_for_a_user_id_that_does_not_exist(login_as, api_client):
    admin = login_as("Administrator")
    response = api_client.get("/api/users/999999", headers=admin["headers"])
    assert response.status_code == 404


def test_only_an_administrator_can_delete_a_user(login_as, api_client):
    """Create a throwaway user and confirm only an Administrator can
    delete it -- a real DELETE, but against data this test created
    itself, never a seeded account.
    """
    username = unique_username("capstone_delete_target")
    created = api_client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "correct-horse-1",
            "role": "Patient",
            "full_name": "Capstone Delete Target",
        },
    )
    user_id = created.json()["userId"]

    nurse = login_as("Nurse")
    denied = api_client.delete(f"/api/users/{user_id}", headers=nurse["headers"])
    assert denied.status_code == 403

    admin = login_as("Administrator")
    allowed = api_client.delete(f"/api/users/{user_id}", headers=admin["headers"])
    assert allowed.status_code == 200

    after_delete = api_client.get(f"/api/users/{user_id}", headers=admin["headers"])
    assert after_delete.status_code == 404
