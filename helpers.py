"""
Shared helper functions used by conftest.py and the test files.

Nothing in here is a pytest fixture on its own -- these are plain, importable
functions. conftest.py wraps the ones that need to be shared state (like the
parsed OpenAPI spec) in a fixture; everything else is just called directly
where it's needed.
"""
from __future__ import annotations

import base64
import json
import re
import time

import httpx

BASE_URL = "http://localhost:5000"


def fetch_openapi_spec(base_url: str = BASE_URL) -> dict:
    """Pull the real OpenAPI spec out of the Swagger UI's init script.

    rbac-healthcare-system doesn't expose a dedicated /api-docs.json or
    /api-docs/swagger.json route -- both just fall through to the Swagger UI's
    HTML shell. The actual spec is embedded as `options.swaggerDoc` inside
    swagger-ui-init.js, generated fresh by swagger-jsdoc on every request.
    """
    response = httpx.get(f"{base_url}/api-docs/swagger-ui-init.js")
    response.raise_for_status()

    match = re.search(
        r"var options = (\{.*?\n\});\n\s*url = options\.swaggerUrl",
        response.text,
        re.DOTALL,
    )
    if not match:
        raise ValueError("Could not find embedded spec in swagger-ui-init.js")

    options = json.loads(match.group(1))
    return options["swaggerDoc"]


def list_operations(spec: dict) -> list[dict]:
    """Walk spec['paths'] into one flat record per (method, path) operation."""
    operations = []
    for path, methods in spec["paths"].items():
        for method, details in methods.items():
            operations.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "summary": details.get("summary", ""),
                    "requires_auth": "security" in details,
                    "responses": sorted(details.get("responses", {}).keys()),
                    "tags": details.get("tags", []),
                }
            )
    return operations


def to_test_case_id(op: dict) -> str:
    """Turn an operation record into a stable, readable identifier."""
    path_slug = op["path"].strip("/").replace("/", "_").replace("{", "").replace("}", "")
    return f"{op['method'].lower()}_{path_slug}"


def decode_jwt_payload(token: str) -> dict:
    """Decode (not verify) the payload segment of a JWT.

    JWTs are signed, not encrypted -- anyone holding the token can read its
    claims without the server's secret. This is used in security tests to
    build a tampered token with the same (now-invalid) signature.
    """
    payload_segment = token.split(".")[1]
    padded = payload_segment + "=" * (-len(payload_segment) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


def forge_tampered_token(token: str, **claim_overrides) -> str:
    """Rebuild a JWT with modified claims but the ORIGINAL (now invalid) signature.

    Used to prove the server actually verifies the signature rather than
    trusting whatever role is in the payload.
    """
    header, payload_segment, signature = token.split(".")
    decoded = decode_jwt_payload(token)
    tampered = {**decoded, **claim_overrides}
    tampered_json = json.dumps(tampered).encode()
    tampered_payload = base64.urlsafe_b64encode(tampered_json).decode().rstrip("=")
    return f"{header}.{tampered_payload}.{signature}"


def wait_until_healthy(url: str, timeout_seconds: int = 30) -> None:
    """Poll a health endpoint until it responds 200, instead of a fixed sleep."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            if httpx.get(url).status_code == 200:
                return
        except httpx.ConnectError:
            pass
        time.sleep(1)
    raise TimeoutError(f"{url} never became healthy within {timeout_seconds}s")


def unique_username(prefix: str = "apitest") -> str:
    """A username guaranteed not to collide with seeded or previously-created data."""
    return f"{prefix}_{int(time.time() * 1_000_000)}"
