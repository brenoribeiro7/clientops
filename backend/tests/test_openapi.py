import json
import subprocess
import sys
from pathlib import Path

from app.cli.export_openapi import generated_schema


def test_openapi_generation_is_deterministic_and_cl04_scoped() -> None:
    first = generated_schema()
    second = generated_schema()
    assert first == second
    schema = json.loads(first)
    assert set(schema["paths"]) == {
        "/api/v1/auth/change-password",
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/auth/session",
        "/api/v1/business-profile",
        "/api/v1/clients",
        "/api/v1/clients/{client_id}",
        "/api/v1/clients/{client_id}/archive",
        "/api/v1/clients/{client_id}/equipment",
        "/api/v1/clients/{client_id}/equipment/{equipment_id}",
        "/api/v1/clients/{client_id}/equipment/{equipment_id}/archive",
        "/api/v1/clients/{client_id}/equipment/{equipment_id}/restore",
        "/api/v1/clients/{client_id}/restore",
        "/api/v1/clients/{client_id}/timeline",
        "/api/v1/health/live",
        "/api/v1/health/ready",
        "/api/v1/public/quote",
        "/api/v1/public/quote/approve",
        "/api/v1/public/quote/logo",
        "/api/v1/quotes",
        "/api/v1/quotes/{quote_id}",
        "/api/v1/quotes/{quote_id}/cancel",
        "/api/v1/quotes/{quote_id}/duplicate",
        "/api/v1/quotes/{quote_id}/logo",
        "/api/v1/quotes/{quote_id}/public-access",
        "/api/v1/quotes/{quote_id}/public-access/{access_id}/revoke",
        "/api/v1/quotes/{quote_id}/send",
        "/api/v1/quotes/{quote_id}/timeline",
        "/api/v1/users",
        "/api/v1/users/{user_id}",
        "/api/v1/users/{user_id}/disable",
        "/api/v1/users/{user_id}/enable",
        "/api/v1/users/{user_id}/reset-password",
    }
    assert schema["components"]["securitySchemes"]["cookieAuth"] == {
        "in": "cookie",
        "name": "__Host-clientops_session",
        "type": "apiKey",
    }
    assert b"ServiceOrder" not in first
    assert b"Evidence" not in first
    assert b"Charge" not in first
    assert b"Alert" not in first
    assert all("delete" not in operations for operations in schema["paths"].values())

    components = schema["components"]["schemas"]
    for patch_name in ("ClientPatch", "EquipmentPatch"):
        patch_schema = components[patch_name]
        name_schema = patch_schema["properties"]["name"]
        assert name_schema["type"] == "string"
        assert "anyOf" not in name_schema
        assert "name" not in patch_schema.get("required", [])

    phone_schema = components["ClientPatch"]["properties"]["phone"]
    assert {variant.get("type") for variant in phone_schema["anyOf"]} == {"string", "null"}

    assert schema["components"]["securitySchemes"]["bearerAuth"] == {
        "scheme": "bearer",
        "type": "http",
    }
    public_paths = (
        "/api/v1/public/quote",
        "/api/v1/public/quote/logo",
        "/api/v1/public/quote/approve",
    )
    for path in public_paths:
        operation = next(iter(schema["paths"][path].values()))
        assert operation["security"] == [{"bearerAuth": []}]
        assert "cookieAuth" not in json.dumps(operation["security"])
        retry_after = operation["responses"]["429"]["headers"]["Retry-After"]
        assert retry_after["schema"]["type"] == "string"

    private_operations = [
        operation
        for path, methods in schema["paths"].items()
        if path.startswith("/api/v1/quotes")
        for operation in methods.values()
    ]
    assert private_operations
    for operation in private_operations:
        assert operation["security"] == [{"cookieAuth": []}]
        assert "bearerAuth" not in json.dumps(operation["security"])

    assert set(components["PublicClient"]["properties"]) == {"name"}
    for schema_name, fields in {
        "QuoteItemData": ("quantity", "unit_price", "line_total"),
        "QuoteItemInput": ("quantity", "unit_price"),
        "QuoteSummary": ("subtotal", "total"),
        "PublicQuoteItem": ("quantity", "unit_price", "line_total"),
        "PublicQuoteData": ("subtotal", "total"),
    }.items():
        for field in fields:
            assert components[schema_name]["properties"][field]["type"] == "string"

    quote_patch = components["QuotePatch"]
    assert not quote_patch.get("required")
    for field in ("client_id", "valid_until", "items"):
        assert "anyOf" not in quote_patch["properties"][field]
    assert {variant.get("type") for variant in quote_patch["properties"]["notes"]["anyOf"]} == {
        "string",
        "null",
    }

    for path, method in (
        ("/api/v1/quotes/{quote_id}", "patch"),
        ("/api/v1/quotes/{quote_id}/send", "post"),
        ("/api/v1/quotes/{quote_id}/cancel", "post"),
    ):
        headers = {
            parameter["name"]: parameter
            for parameter in schema["paths"][path][method]["parameters"]
            if parameter["in"] == "header"
        }
        assert "If-Match" in headers
    for path, method in (
        ("/api/v1/quotes/{quote_id}", "get"),
        ("/api/v1/quotes/{quote_id}", "patch"),
        ("/api/v1/quotes/{quote_id}/cancel", "post"),
    ):
        assert "ETag" in schema["paths"][path][method]["responses"]["200"]["headers"]


def test_openapi_check_rejects_a_stale_copy(tmp_path: Path) -> None:
    stale = tmp_path / "openapi.json"
    stale.write_text("{}\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "app.cli.export_openapi", "--check", str(stale)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "desatualizada" in result.stderr
