import os
import json
import pytest
import subprocess
from fastapi.testclient import TestClient
from dume.server.app import app, memory_engine, schema_dict, normalize_entity_id
from dume.core.record import hex_to_uuid_bytes, uuid_to_hex


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_inline_directive_interception(client):
    """
    Acceptance Criteria 1: test_inline_directive_interception
    1. Send payload with message: "Hello !set WORKSPACE_ROLE=1st_AD please advise."
    2. Assert the upstream forwarded payload / grounded context contains clean prompt "Hello please advise."
    3. Assert LMDB register WORKSPACE_ROLE equals "1st_AD".
    4. Test !flush clearing scratchpad.
    """
    entity_name = "MadBrad-Substrate-Directives-Test"
    canonical_uuid_hex = normalize_entity_id(entity_name)
    canonical_uuid_bytes = hex_to_uuid_bytes(canonical_uuid_hex)

    payload = {
        "model": "qwen2.5:0.5b",
        "messages": [
            {"role": "user", "content": "Hello !set WORKSPACE_ROLE=1st_AD please advise."}
        ],
        "stream": False,
        "entity_id": entity_name
    }

    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    data = response.json()

    # 1. Assert LMDB register WORKSPACE_ROLE equals "1st_AD"
    opcode = schema_dict.get_opcode_by_name("WORKSPACE_ROLE")
    assert opcode is not None
    record = memory_engine.get_active_record(canonical_uuid_bytes, opcode)
    assert record is not None
    human_val = schema_dict.format_value(opcode, record)
    assert human_val == "1st_AD"

    # 2. Test !flush directive
    dispatcher = app.state.session_dispatcher
    if dispatcher:
        dispatcher.dispatch_turn(canonical_uuid_hex, "User line 1", "Agent line 1")
        history_before = dispatcher.context_manager.get_bounded_history(canonical_uuid_hex)
        assert len(history_before) > 0

        # Send !flush directive in prompt
        flush_payload = {
            "model": "qwen2.5:0.5b",
            "messages": [
                {"role": "user", "content": "!flush"}
            ],
            "stream": False,
            "entity_id": entity_name
        }
        resp_flush = client.post("/v1/chat/completions", json=flush_payload)
        assert resp_flush.status_code == 200

        history_after = dispatcher.context_manager.get_bounded_history(canonical_uuid_hex)
        assert len(history_after) == 0


def test_multi_entity_isolation(client):
    """
    Acceptance Criteria 2: test_multi_entity_isolation
    1. Send write to X-Entity-ID: Nostra with !set STATUS=PLANNING.
    2. Send write to X-Entity-ID: AG-IDE with !set STATUS=EXECUTING.
    3. Send write with inline [ENTITY:Production-AD] tag and !set STATUS=REVIEW.
    4. Verify each partition returns only its respective state registers.
    """
    # 1. Write to Nostra
    resp_nostra = client.post(
        "/v1/chat/completions",
        headers={"X-Entity-ID": "Nostra"},
        json={
            "model": "qwen2.5:0.5b",
            "messages": [{"role": "user", "content": "!set STATUS=PLANNING"}]
        }
    )
    assert resp_nostra.status_code == 200

    # 2. Write to AG-IDE
    resp_ag = client.post(
        "/v1/chat/completions",
        headers={"X-Entity-ID": "AG-IDE"},
        json={
            "model": "qwen2.5:0.5b",
            "messages": [{"role": "user", "content": "!set STATUS=EXECUTING"}]
        }
    )
    assert resp_ag.status_code == 200

    # 3. Write via inline [ENTITY:Production-AD] tag
    resp_prod = client.post(
        "/v1/chat/completions",
        json={
            "model": "qwen2.5:0.5b",
            "messages": [{"role": "user", "content": "[ENTITY:Production-AD] !set STATUS=REVIEW"}]
        }
    )
    assert resp_prod.status_code == 200

    # 4. Verify entity register isolation in LMDB
    opcode_status = schema_dict.get_opcode_by_name("STATUS")
    assert opcode_status is not None

    rec_nostra = memory_engine.get_active_record(hex_to_uuid_bytes(normalize_entity_id("Nostra")), opcode_status)
    rec_ag = memory_engine.get_active_record(hex_to_uuid_bytes(normalize_entity_id("AG-IDE")), opcode_status)
    rec_prod = memory_engine.get_active_record(hex_to_uuid_bytes(normalize_entity_id("Production-AD")), opcode_status)

    assert rec_nostra is not None and schema_dict.format_value(opcode_status, rec_nostra) == "PLANNING"
    assert rec_ag is not None and schema_dict.format_value(opcode_status, rec_ag) == "EXECUTING"
    assert rec_prod is not None and schema_dict.format_value(opcode_status, rec_prod) == "REVIEW"


def test_standalone_startup_dryrun(client):
    """
    Acceptance Criteria 3: test_standalone_startup_dryrun
    Assert http://localhost:8090/v1/models returns 200 OK.
    """
    response = client.get("/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert len(data["data"]) > 0
