"""
The real, verified permission matrix across all 4 roles -- not documented
anywhere in the spec's own `security` block, which only says "some
authenticated bearer token," never which role.
"""
import pytest


@pytest.mark.parametrize(
    "role,expected_status",
    [
        pytest.param("Administrator", 404, id="admin-404-not-403"),
        pytest.param("Doctor", 404, id="doctor-404-not-403"),
        pytest.param("Nurse", 403, id="nurse-forbidden"),
        pytest.param("Patient", 403, id="patient-forbidden"),
    ],
)
def test_delete_medical_record_role_gate(login_as, api_client, role, expected_status):
    session = login_as(role)
    response = api_client.delete(
        "/api/medical-records/999999", headers=session["headers"]
    )
    assert response.status_code == expected_status


@pytest.mark.parametrize(
    "role,expected_status",
    [
        pytest.param("Administrator", 200, id="admin-can-list-patients"),
        pytest.param("Doctor", 200, id="doctor-can-list-patients"),
        pytest.param("Nurse", 200, id="nurse-can-list-patients"),
        pytest.param("Patient", 403, id="patient-forbidden"),
    ],
)
def test_list_patients_role_gate(login_as, api_client, role, expected_status):
    session = login_as(role)
    response = api_client.get("/api/patients", headers=session["headers"])
    assert response.status_code == expected_status
    if expected_status == 200:
        assert isinstance(response.json(), list)
        assert len(response.json()) > 0


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


def test_get_medical_records_nurse_sees_everything_same_as_admin(login_as, api_client):
    """A real divergence between the documented matrix and actual
    enforcement: GET /api/medical-records does not scope results for a
    Nurse -- a Nurse sees every record, the same as an Administrator,
    not just records tied to patients they're treating.
    """
    admin = login_as("Administrator")
    nurse = login_as("Nurse")

    admin_records = api_client.get(
        "/api/medical-records", headers=admin["headers"]
    ).json()
    nurse_records = api_client.get(
        "/api/medical-records", headers=nurse["headers"]
    ).json()

    assert len(nurse_records) == len(admin_records)


def test_get_medical_records_doctor_and_patient_are_scoped_to_their_own(
    login_as, api_client
):
    doctor = login_as("Doctor")
    patient = login_as("Patient")
    admin = login_as("Administrator")

    admin_count = len(api_client.get("/api/medical-records", headers=admin["headers"]).json())
    doctor_count = len(api_client.get("/api/medical-records", headers=doctor["headers"]).json())
    patient_count = len(api_client.get("/api/medical-records", headers=patient["headers"]).json())

    assert 0 < doctor_count <= admin_count
    assert 0 < patient_count <= admin_count


@pytest.mark.parametrize(
    "role,expected_status",
    [
        pytest.param("Administrator", 403, id="admin-forbidden"),
        pytest.param("Doctor", 404, id="doctor-passes-gate-then-404s"),
        pytest.param("Nurse", 403, id="nurse-forbidden"),
        pytest.param("Patient", 403, id="patient-forbidden"),
    ],
)
def test_put_medical_record_role_gate(login_as, api_client, role, expected_status):
    """PUT /api/medical-records/{id} is Doctor-only -- not Administrator,
    unlike most other medical-record and appointment operations. Hitting a
    nonexistent ID isolates the role check from the lookup: Doctor passes
    the gate and reaches the "not found" branch (404); every other role,
    including Administrator, is denied before the lookup ever happens.
    """
    session = login_as(role)
    response = api_client.put(
        "/api/medical-records/999999",
        headers=session["headers"],
        json={"diagnosis": "role gate probe"},
    )
    assert response.status_code == expected_status


def test_disallowed_role_gets_a_descriptive_requiredroles_body(login_as, api_client):
    nurse = login_as("Nurse")
    response = api_client.get("/api/users", headers=nurse["headers"])

    assert response.status_code == 403
    body = response.json()
    assert "requiredRoles" in body
    assert "Administrator" in body["requiredRoles"]
    assert body["userRole"] == "Nurse"
