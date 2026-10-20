import os
import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from dume.intake.scrubber import EnterpriseScrubber
from dume.intake.pr_reducer import PRReducer
from dume.intake.error_reducer import ErrorReducer
from dume.intake.incident_reducer import IncidentReducer
from dume.mcp_server import (
    dume_read_adr,
    dume_get_error_details,
    dume_get_incident_rca,
    dume_list_module_context,
    dume_read_state,
    dume_commit_state,
)
from dume.server.app import app


@pytest.fixture
def client():
    os.environ["DUME_TESTING"] = "1"
    with TestClient(app) as test_client:
        yield test_client


def test_enterprise_scrubber():
    """
    Tests EnterpriseScrubber for scrubbing PII, credentials, IP addresses, internal DNS, and credit cards.
    """
    scrubber = EnterpriseScrubber()

    # 1. Valid Credit Card (Visa test number: 4532 0151 1283 0366) vs timestamp / non-card number
    raw_cc = "User paid with card 4532015112830366 on timestamp 20260905120000."
    scrubbed_cc = scrubber.scrub(raw_cc)
    assert "[REDACTED_PAN]" in scrubbed_cc
    assert "4532015112830366" not in scrubbed_cc
    assert "20260905120000" in scrubbed_cc  # Non-luhn string preserved

    # 2. Email Address & Private IP
    raw_email_ip = "Contact john.doe@internal-company.corp or server 10.0.4.15 and 192.168.1.100."
    scrubbed_email_ip = scrubber.scrub(raw_email_ip)
    assert "[REDACTED_EMAIL]" in scrubbed_email_ip
    assert "[REDACTED_IP]" in scrubbed_email_ip
    assert "john.doe@internal-company.corp" not in scrubbed_email_ip
    assert "10.0.4.15" not in scrubbed_email_ip
    assert "192.168.1.100" not in scrubbed_email_ip

    # 3. JWT Token & API Keys
    mock_stripe_key = "sk_" + "test_" + "51abcdefGHIJKL1234567890"
    raw_creds = (
        "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature "
        f"and Stripe key {mock_stripe_key} and AWS AKIAIOSFODNN7EXAMPLE"
    )
    scrubbed_creds = scrubber.scrub(raw_creds)
    assert "[REDACTED_JWT]" in scrubbed_creds or "[REDACTED_TOKEN]" in scrubbed_creds
    assert "[REDACTED_API_KEY]" in scrubbed_creds
    assert mock_stripe_key not in scrubbed_creds
    assert "AKIAIOSFODNN7EXAMPLE" not in scrubbed_creds

    # 4. Internal DNS
    raw_dns = "Connecting to DB host db-primary.internal.local or redis.corp.local"
    scrubbed_dns = scrubber.scrub(raw_dns)
    assert "[REDACTED_DNS]" in scrubbed_dns
    assert "db-primary.internal.local" not in scrubbed_dns


def test_pr_reducer_and_adr_generation():
    """
    Tests PRReducer parsing PR/design proposal JSON payload, creating an ADR card in ~/.dume/assets/adrs/,
    and committing registers to active state.
    """
    pr_payload = {
        "pr_id": "PR-892",
        "title": "Migrate In-Memory Cache to Redis Cluster",
        "module": "storage_cache",
        "author": "engineer@company.com",
        "summary": "Switch caching substrate from local dict to Redis cluster. Connecting to 10.0.2.55.",
        "decision": "Use Redis cluster for horizontal scalability.",
        "status": "APPROVED"
    }

    registers, asset_path = PRReducer.reduce_pr_payload(pr_payload, entity_id="TestEntity-PR")

    assert Path(asset_path).exists()
    card_content = Path(asset_path).read_text(encoding="utf-8")

    # Verify PII scrubbed in card
    assert "engineer@company.com" not in card_content
    assert "[REDACTED_EMAIL]" in card_content
    assert "10.0.2.55" not in card_content
    assert "[REDACTED_IP]" in card_content

    # Verify registers returned
    assert registers.get("CURRENT_MODULE") == "storage_cache"
    assert registers.get("ACTIVE_ADR").startswith("ADR_PR-892")
    assert "ADR_PATH" in registers


def test_error_reducer_and_fingerprint():
    """
    Tests ErrorReducer processing APM stack traces, extracting failing method,
    fingerprinting, saving markdown in ~/.dume/assets/errors/, and building registers.
    """
    error_payload = {
        "error_class": "ZeroDivisionError",
        "message": "division by zero in calculate_ratio()",
        "failing_method": "dume.core.record.calculate_ratio",
        "count_24h": 42,
        "stack_trace": "Traceback (most recent call last):\n  File 'dume/core/record.py', line 15, in calculate_ratio\n    return val / 0\nZeroDivisionError: division by zero",
        "user_email": "user@test.org"
    }

    registers, asset_path = ErrorReducer.reduce_error_payload(error_payload, entity_id="TestEntity-Error")

    assert Path(asset_path).exists()
    card_content = Path(asset_path).read_text(encoding="utf-8")

    assert "user@test.org" not in card_content
    assert "[REDACTED_EMAIL]" in card_content
    assert "ZeroDivisionError" in card_content

    assert registers.get("ERROR_CLASS") == "ZeroDivisionError"
    assert registers.get("FAILING_METHOD") == "dume.core.record.calculate_ratio"
    assert registers.get("ERROR_COUNT_24H") == 42
    assert "ERROR_FINGERPRINT" in registers
    assert "ERROR_CARD_PATH" in registers


def test_incident_reducer():
    """
    Tests IncidentReducer processing ticket postmortem/runbook payload, writing
    to ~/.dume/assets/incidents/, and outputting registers.
    """
    incident_payload = {
        "incident_id": "INC-4091",
        "title": "LMDB Lock Contention Outage",
        "severity": "CRITICAL",
        "root_cause": "Multiple processes attempted write transactions simultaneously without lock timeout.",
        "workaround": "Set DUME_LMDB_MAX_READERS=256 and restart service.",
        "status": "RESOLVED"
    }

    registers, asset_path = IncidentReducer.reduce_incident_payload(incident_payload, entity_id="TestEntity-Inc")

    assert Path(asset_path).exists()
    card_content = Path(asset_path).read_text(encoding="utf-8")
    assert "LMDB Lock Contention Outage" in card_content

    assert registers.get("ACTIVE_INCIDENT") == "INC-4091"
    assert registers.get("SEVERITY") == "CRITICAL"
    assert "ROOT_CAUSE" in registers
    assert "WORKAROUND_STATUS" in registers
    assert "INCIDENT_PATH" in registers


def test_mcp_enterprise_tools():
    """
    Tests the FastMCP enterprise tools: dume_read_adr, dume_get_error_details,
    dume_get_incident_rca, and dume_list_module_context.
    """
    # 1. Create dummy assets
    adrs_dir = Path.home() / ".dume" / "assets" / "adrs"
    errors_dir = Path.home() / ".dume" / "assets" / "errors"
    incidents_dir = Path.home() / ".dume" / "assets" / "incidents"
    adrs_dir.mkdir(parents=True, exist_ok=True)
    errors_dir.mkdir(parents=True, exist_ok=True)
    incidents_dir.mkdir(parents=True, exist_ok=True)

    (adrs_dir / "ADR_999_test_architecture.md").write_text("# ADR 999: Test Architecture\nContent here.", encoding="utf-8")
    (errors_dir / "ERR_ABC123.md").write_text("# ERR_ABC123: NullPointerInTest\nStack trace here.", encoding="utf-8")
    (incidents_dir / "INC_888.md").write_text("# INC_888: Database Timeout\nRCA here.", encoding="utf-8")

    # 2. Test reading individual cards via MCP tools
    adr_res = dume_read_adr("999")
    assert "# ADR 999: Test Architecture" in adr_res

    err_res = dume_get_error_details("ABC123")
    assert "NullPointerInTest" in err_res

    inc_res = dume_get_incident_rca("888")
    assert "Database Timeout" in inc_res

    # 3. Test listing module context
    ctx = dume_list_module_context("test")
    assert len(ctx["adrs"]) >= 1
    assert any("999" in item["file"] for item in ctx["adrs"])


def test_rest_api_enterprise_endpoints(client):
    """
    Tests REST API endpoints /api/intake/enterprise, /api/assets/list, and /api/assets/read.
    """
    # 1. Post to /api/intake/enterprise
    resp = client.post(
        "/api/intake/enterprise",
        json={
            "entity_id": "MadBrad-Nostra-01",
            "intake_type": "pr",
            "payload": {
                "pr_id": "PR-555",
                "title": "Implement Enterprise Diagnostic Explorer",
                "summary": "Added PII scrubber and assets reader.",
                "decision": "Store cards off-bus in ~/.dume/assets/."
            }
        }
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["committed_count"] > 0
    assert "asset_path" in body

    # 2. GET /api/assets/list
    list_resp = client.get("/api/assets/list")
    assert list_resp.status_code == 200
    list_body = list_resp.json()
    assert list_body["count"] > 0
    assert len(list_body["assets"]) > 0

    # 3. GET /api/assets/read
    sample_asset = list_body["assets"][0]
    read_resp = client.get(f"/api/assets/read?category={sample_asset['category']}s&filename={sample_asset['filename']}")
    assert read_resp.status_code == 200
    read_body = read_resp.json()
    assert "content" in read_body
    assert read_body["filename"] == sample_asset["filename"]
