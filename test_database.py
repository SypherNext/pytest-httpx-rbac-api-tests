"""
Verifying writes by querying the real SQLite file directly, not just by
trusting the API's own GET handler to report the truth about what it did.
"""
import pytest


@pytest.mark.db
def test_creates_an_appointment_and_confirms_the_row_directly_in_sqlite(
    login_as, get_first_user_with_role, api_client, db_query
):
    patient = get_first_user_with_role("Patient")
    doctor = get_first_user_with_role("Doctor")
    admin = login_as("Administrator")

    created = api_client.post(
        "/api/appointments",
        headers=admin["headers"],
        json={
            "patient_id": patient["id"],
            "doctor_id": doctor["id"],
            "appointment_date": "2026-09-12T10:00:00",
            "reason": "db-verification test",
        },
    )
    assert created.status_code == 201

    row = db_query(
        "SELECT * FROM appointments WHERE id = ?", (created.json()["appointmentId"],)
    )

    assert row is not None
    assert row["patient_id"] == patient["id"]
    assert row["doctor_id"] == doctor["id"]
    assert row["reason"] == "db-verification test"
    assert row["status"] == "scheduled"


@pytest.mark.db
def test_update_through_the_api_persists_in_the_real_row(
    login_as, get_first_user_with_role, api_client, db_query
):
    doctor = login_as("Doctor")
    patient = get_first_user_with_role("Patient")

    created = api_client.post(
        "/api/medical-records",
        headers=doctor["headers"],
        json={"patient_id": patient["id"], "diagnosis": "initial diagnosis"},
    )
    record_id = created.json()["recordId"]

    api_client.put(
        f"/api/medical-records/{record_id}",
        headers=doctor["headers"],
        json={"diagnosis": "updated via API"},
    )

    row = db_query("SELECT * FROM medical_records WHERE id = ?", (record_id,))

    assert row is not None
    assert row["diagnosis"] == "updated via API"
    assert row["updated_at"] is not None


@pytest.mark.db
def test_delete_through_the_api_actually_removes_the_row(
    login_as, get_first_user_with_role, api_client, db_query
):
    admin = login_as("Administrator")
    patient = get_first_user_with_role("Patient")
    doctor = get_first_user_with_role("Doctor")

    created = api_client.post(
        "/api/appointments",
        headers=admin["headers"],
        json={
            "patient_id": patient["id"],
            "doctor_id": doctor["id"],
            "appointment_date": "2026-09-13T10:00:00",
            "reason": "db-deletion test",
        },
    )
    appointment_id = created.json()["appointmentId"]

    api_client.delete(f"/api/appointments/{appointment_id}", headers=admin["headers"])

    row = db_query("SELECT * FROM appointments WHERE id = ?", (appointment_id,))
    assert row is None
