"""
A small, deliberately shallow set of checks -- is the app fundamentally
up? -- plus basic response-time sanity assertions that catch something
going catastrophically wrong, not minor regressions.
"""
import time

import pytest


@pytest.mark.smoke
def test_health_endpoint_is_up(api_client):
    response = api_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "OK", "message": "Server is running"}


@pytest.mark.smoke
def test_login_works(api_client):
    response = api_client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert response.status_code == 200


@pytest.mark.smoke
def test_login_responds_within_a_reasonable_budget(api_client):
    start = time.perf_counter()
    response = api_client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    )
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert response.status_code == 200
    assert elapsed_ms < 1000  # generous on purpose: catches catastrophic regressions


@pytest.mark.smoke
def test_list_patients_responds_within_a_reasonable_budget(login_as, api_client):
    admin = login_as("Administrator")

    start = time.perf_counter()
    response = api_client.get("/api/patients", headers=admin["headers"])
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert response.status_code == 200
    assert elapsed_ms < 1000
