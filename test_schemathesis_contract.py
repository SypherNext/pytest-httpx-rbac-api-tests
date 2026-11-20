"""
Property-based, spec-driven testing with Schemathesis: instead of hand-picked
inputs, generate many varied ones straight from the OpenAPI schema and check
that every response matches what the spec actually documents.

Safety note specific to this app: rbac-healthcare-system is a real, shared,
stateful SQLite-backed dev server with no per-test database reset. Random
fuzzing against write operations (DELETE, PUT, POST) with a real admin
token can and will delete or corrupt real seeded accounts if a generated
path parameter happens to land on an existing ID -- this isn't
hypothetical, it happened once while building this exact suite (a
generated DELETE against /api/users/{id} deleted the real admin account).
The broad contract check below is deliberately restricted to GET requests,
which are read-only by definition. Every write operation already has
dedicated, controlled hand-written coverage elsewhere in this suite
(test_appointments.py, test_medical_records.py, test_negative.py).
"""
import schemathesis
from schemathesis import GenerationMode

from helpers import fetch_openapi_spec

BASE_URL = "http://localhost:5000"


def _build_schema():
    raw_spec = fetch_openapi_spec(BASE_URL)
    schema = (
        schemathesis.openapi.from_dict(raw_spec)
        .exclude(method="DELETE")
        .exclude(method="PUT")
        .exclude(method="POST")
    )

    import httpx

    token = httpx.post(
        f"{BASE_URL}/api/auth/login", json={"username": "admin", "password": "admin123"}
    ).json()["token"]

    schema.config.update(base_url=BASE_URL, headers={"Authorization": f"Bearer {token}"})
    schema.config.generation.update(
        modes=[GenerationMode.POSITIVE],
        with_security_parameters=False,
        max_examples=5,
        deterministic=True,
    )
    return schema


schema = _build_schema()


@schema.parametrize()
def test_api_matches_its_own_spec(case):
    # Using the Administrator's token runs every operation with the most
    # permissive role -- this checks "does the response shape match the
    # spec," not "does the right role get denied" (that's test_rbac_matrix.py).
    # ignored_auth is excluded because this course's own security tests
    # (test_security.py) already cover invalid-auth behavior explicitly.
    case.call_and_validate(excluded_checks=[schemathesis.checks.ignored_auth])


def test_missing_patient_id_now_returns_a_clean_400(
    login_as, get_first_user_with_role, api_client
):
    """The same gap test_appointments.py covers by hand: POST
    /api/appointments used to have no validation layer, so a request
    missing the NOT NULL patient_id column failed at the database with a
    raw 500 instead of a documented, clean 400. Fixed. Demonstrated here as
    a single, deliberately constructed case rather than broad random
    fuzzing -- this route stays excluded from the sweep above regardless,
    since broad write-operation fuzzing against this real shared dev server
    is unsafe independent of this specific gap being fixed.
    """
    admin = login_as("Administrator")
    doctor = get_first_user_with_role("Doctor")
    response = api_client.post(
        "/api/appointments",
        headers=admin["headers"],
        json={
            "doctor_id": doctor["id"],
            "appointment_date": "2026-09-01T10:00:00",
            "reason": "schemathesis gap rediscovery",
            # patient_id deliberately omitted, same as the hand-written case
        },
    )
    assert response.status_code == 400
