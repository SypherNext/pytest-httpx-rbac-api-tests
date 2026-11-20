"""
CRUD lifecycle for /api/medical-records, Doctor-only write access, and the
real gap where the spec marks `diagnosis` required but the route doesn't
enforce it.
"""
import jsonschema


def test_medical_record_crud_lifecycle(login_as, get_first_user_with_role, api_client):
    doctor = login_as("Doctor")
    patient = get_first_user_with_role("Patient")

    created = api_client.post(
        "/api/medical-records",
        headers=doctor["headers"],
        json={
            "patient_id": patient["id"],
            "diagnosis": "Seasonal allergies",
            "prescription": "Loratadine 10mg",
        },
    )
    assert created.status_code == 201
    record_id = created.json()["recordId"]

    after_create = api_client.get(
        f"/api/medical-records/{record_id}", headers=doctor["headers"]
    )
    assert after_create.json()["diagnosis"] == "Seasonal allergies"
    assert after_create.json()["notes"] is None

    updated = api_client.put(
        f"/api/medical-records/{record_id}",
        headers=doctor["headers"],
        json={
            "diagnosis": "Seasonal allergies (resolved)",
            "prescription": "Loratadine 10mg",
            "notes": "Follow up in 2 weeks",
        },
    )
    assert updated.status_code == 200

    after_update = api_client.get(
        f"/api/medical-records/{record_id}", headers=doctor["headers"]
    )
    assert after_update.json()["diagnosis"] == "Seasonal allergies (resolved)"
    assert after_update.json()["notes"] == "Follow up in 2 weeks"

    deleted = api_client.delete(
        f"/api/medical-records/{record_id}", headers=doctor["headers"]
    )
    assert deleted.status_code == 200

    after_delete = api_client.get(
        f"/api/medical-records/{record_id}", headers=doctor["headers"]
    )
    assert after_delete.status_code == 404


def test_medical_record_payload_matches_spec_schema(openapi_spec):
    schema = openapi_spec["paths"]["/api/medical-records"]["post"]["requestBody"][
        "content"
    ]["application/json"]["schema"]

    valid_payload = {
        "patient_id": 20,
        "diagnosis": "Seasonal allergies",
        "prescription": "Loratadine 10mg",
    }
    jsonschema.validate(instance=valid_payload, schema=schema)

    invalid_payload = {"patient_id": 20}  # missing required "diagnosis"
    try:
        jsonschema.validate(instance=invalid_payload, schema=schema)
        assert False, "expected validation to fail"
    except jsonschema.ValidationError as exc:
        assert "diagnosis" in str(exc)


def test_create_without_required_diagnosis_field_returns_a_clean_400(
    login_as, get_first_user_with_role, api_client
):
    """The spec marks `diagnosis` as required. This route used to have no
    validation enforcing that -- it just built an INSERT straight from the
    request body, and `diagnosis` being a NOT NULL column meant a missing
    value failed at the database as a raw 500. That gap is fixed: a missing
    required field is now rejected with a clean 400 before the query runs.
    """
    doctor = login_as("Doctor")
    patient = get_first_user_with_role("Patient")

    response = api_client.post(
        "/api/medical-records",
        headers=doctor["headers"],
        json={"patient_id": patient["id"]},  # diagnosis deliberately omitted
    )

    assert response.status_code == 400


def test_create_rejects_a_patient_id_that_does_not_exist(login_as, api_client):
    """There used to be no foreign-key check on patient_id, so a record
    could be created against a patient that doesn't exist -- it still
    returned 201, so nothing about the status code looked wrong. Fixed:
    patient_id is now validated against a real Patient user first.
    """
    doctor = login_as("Doctor")

    response = api_client.post(
        "/api/medical-records",
        headers=doctor["headers"],
        json={"patient_id": 999999, "diagnosis": "ghost patient test"},
    )

    assert response.status_code == 400


def test_only_a_doctor_can_create_a_medical_record(
    login_as, get_first_user_with_role, api_client
):
    patient = get_first_user_with_role("Patient")

    for role in ("Administrator", "Nurse", "Patient"):
        session = login_as(role)
        response = api_client.post(
            "/api/medical-records",
            headers=session["headers"],
            json={"patient_id": patient["id"], "diagnosis": "role-gate check"},
        )
        assert response.status_code == 403, f"{role} should not be able to create a record"
