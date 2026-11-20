"""
CRUD lifecycle, schema validation, and the real-app quirks around
/api/appointments: no role gate on creation, and a raw 500 for a missing
required field since the route has no validation layer at all.
"""
from typing import Optional

import pytest
from pydantic import BaseModel


class Appointment(BaseModel):
    id: int
    patient_id: int
    doctor_id: int
    appointment_date: str
    status: str
    reason: Optional[str] = None
    notes: Optional[str] = None
    patient_name: str
    doctor_name: str


def test_appointment_crud_lifecycle(login_as, get_first_user_with_role, api_client):
    nurse = login_as("Nurse")  # nurses are allowed to manage appointments
    patient = get_first_user_with_role("Patient")
    doctor = get_first_user_with_role("Doctor")

    created = api_client.post(
        "/api/appointments",
        headers=nurse["headers"],
        json={
            "patient_id": patient["id"],
            "doctor_id": doctor["id"],
            "appointment_date": "2026-12-01T10:00:00",
            "reason": "pytest crud lifecycle",
        },
    )
    assert created.status_code == 201
    appointment_id = created.json()["appointmentId"]

    after_create = api_client.get(
        f"/api/appointments/{appointment_id}", headers=nurse["headers"]
    )
    assert after_create.status_code == 200
    assert after_create.json()["status"] == "scheduled"

    updated = api_client.put(
        f"/api/appointments/{appointment_id}",
        headers=nurse["headers"],
        json={"status": "completed", "notes": "patient seen"},
    )
    assert updated.status_code == 200

    after_update = api_client.get(
        f"/api/appointments/{appointment_id}", headers=nurse["headers"]
    )
    assert after_update.json()["status"] == "completed"
    assert after_update.json()["notes"] == "patient seen"

    # A real, verified divergence: nurses cannot delete appointments, even
    # though they can create and update them.
    nurse_delete = api_client.delete(
        f"/api/appointments/{appointment_id}", headers=nurse["headers"]
    )
    assert nurse_delete.status_code == 403

    doctor = login_as("Doctor")
    doctor_delete = api_client.delete(
        f"/api/appointments/{appointment_id}", headers=doctor["headers"]
    )
    assert doctor_delete.status_code == 200

    after_delete = api_client.get(
        f"/api/appointments/{appointment_id}", headers=doctor["headers"]
    )
    assert after_delete.status_code == 404


def test_every_appointment_in_the_list_matches_the_contract(login_as, api_client):
    admin = login_as("Administrator")
    response = api_client.get("/api/appointments", headers=admin["headers"])

    appointments = [Appointment.model_validate(item) for item in response.json()]
    assert len(appointments) > 0


def test_a_patient_sees_only_their_own_appointments(login_as, api_client):
    patient = login_as("Patient")

    response = api_client.get("/api/appointments", headers=patient["headers"])

    assert response.status_code == 200
    appointments = response.json()
    assert len(appointments) > 0
    assert all(appt["patient_id"] == patient["user_id"] for appt in appointments)


@pytest.mark.parametrize(
    "role",
    [
        pytest.param("Administrator", id="admin-can-create"),
        pytest.param("Doctor", id="doctor-can-create"),
        pytest.param("Nurse", id="nurse-can-create"),
        pytest.param("Patient", id="patient-can-create"),
    ],
)
def test_post_appointments_has_no_role_gate(
    login_as, get_first_user_with_role, api_client, role
):
    """Documenting real behavior: every authenticated role can create an
    appointment, even Patient -- there's no role check on this route at all.
    """
    session = login_as(role)
    patient = get_first_user_with_role("Patient")
    doctor = get_first_user_with_role("Doctor")

    response = api_client.post(
        "/api/appointments",
        headers=session["headers"],
        json={
            "patient_id": patient["id"],
            "doctor_id": doctor["id"],
            "appointment_date": "2026-12-05T10:00:00",
            "reason": f"role-gate check as {role}",
        },
    )
    assert response.status_code == 201


def test_missing_required_field_returns_a_clean_400(
    login_as, get_first_user_with_role, api_client
):
    """This route used to have no input validation layer at all, so a missing
    NOT NULL column failed at the database with a raw 500. That gap is fixed:
    a missing required field is now rejected with a clean 400 before the
    query ever runs.
    """
    admin = login_as("Administrator")
    doctor = get_first_user_with_role("Doctor")
    response = api_client.post(
        "/api/appointments",
        headers=admin["headers"],
        json={
            "doctor_id": doctor["id"],
            "appointment_date": "2026-09-01T10:00:00",
            "reason": "test",
            # patient_id deliberately omitted
        },
    )

    assert response.status_code == 400
