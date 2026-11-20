"""
Two tools for two different jobs: jsonschema validates request bodies
directly against the spec's own declared schema; Pydantic models fill the
gap where the spec declares no response schema at all.
"""
import jsonschema
import pytest
from pydantic import BaseModel

from helpers import list_operations, to_test_case_id


class LoginUser(BaseModel):
    id: int
    username: str
    email: str
    role: str
    full_name: str


class LoginResponse(BaseModel):
    token: str
    user: LoginUser


def test_login_response_matches_hand_written_contract(api_client):
    response = api_client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    )

    parsed = LoginResponse.model_validate(response.json())
    assert parsed.user.role == "Administrator"


def test_register_payload_matches_spec_schema(openapi_spec):
    schema = openapi_spec["paths"]["/api/auth/register"]["post"]["requestBody"][
        "content"
    ]["application/json"]["schema"]

    valid_payload = {
        "username": "schema_check_user",
        "email": "schema_check@example.com",
        "password": "correct-horse-1",
        "role": "Patient",
        "full_name": "Schema Check",
    }
    jsonschema.validate(instance=valid_payload, schema=schema)


def test_response_status_is_one_the_spec_documents(login_as, api_client, openapi_spec):
    documented = set(
        openapi_spec["paths"]["/api/medical-records/{id}"]["get"]["responses"].keys()
    )
    assert documented == {"200", "404"}

    doctor = login_as("Doctor")
    response = api_client.get("/api/medical-records/999999", headers=doctor["headers"])
    assert str(response.status_code) in documented


def test_the_spec_declares_eleven_distinct_paths(openapi_spec):
    assert len(openapi_spec["paths"]) == 11


def test_operation_checklist_ids_are_all_unique(openapi_spec):
    operations = list_operations(openapi_spec)
    checklist = {to_test_case_id(op): op for op in operations}

    assert len(operations) == 19
    assert len(checklist) == len(operations)
    assert "post_api_medical-records" in checklist
    assert "delete_api_appointments_id" in checklist
