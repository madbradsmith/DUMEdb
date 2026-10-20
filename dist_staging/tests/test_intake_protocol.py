import json
import pytest
from fastapi.testclient import TestClient

from dume.server.app import app, memory_engine, schema_dict, session_dispatcher, normalize_entity_id
from dume.proxy.parser import InlineDirectiveParser
from dume.core.record import UnitRecord, hex_to_uuid_bytes, uuid_to_hex


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_batch_commit_transaction(client):
    """
    Acceptance Test 1: test_batch_commit_transaction
    - Send payload with 10 key-value pairs across different data types (strings, ints, floats, bools).
    - Assert all 10 write to LMDB in a single transaction with identical timestamps.
    """
    entity_name = "MadBrad-Batch-Test-01"
    canonical_uuid = normalize_entity_id(entity_name)

    registers_payload = {
        "DIRECTOR_NAME": "Sarah Connor",
        "WRAP_TIME_EST": 1900,
        "SHUTTER_ANGLE": 180.5,
        "NIGHT_SHOOT_ENABLED": True,
        "SCENE_COUNT": 14,
        "CAMERA_MODEL": "RED V-Raptor",
        "AUDIO_CHANNELS": 4,
        "PRODUCER_NOTE": "Keep noise low after 2200",
        "FRAME_RATE": 23.976,
        "IS_PRODUCTION_LOCKED": False
    }

    payload = {
        "entity_id": entity_name,
        "registers": registers_payload,
        "flush_scratchpad": False
    }

    response = client.post("/v1/dume/state/batch", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "success"
    assert data["entity_id"] == canonical_uuid
    assert data["committed_count"] == 10

    # Verify all records written to LMDB have identical timestamps
    records = data["records"]
    assert len(records) == 10
    timestamps = set(r["timestamp"] for r in records)
    assert len(timestamps) == 1, f"Expected single transaction timestamp, got multiple: {timestamps}"

    # Verify LMDB active state retrieval
    active_recs = memory_engine.get_all_active_registers(hex_to_uuid_bytes(canonical_uuid))
    assert len(active_recs) >= 10


def test_intake_directive_stripping_and_dispatch(client):
    """
    Acceptance Test 2: test_intake_directive_stripping_and_dispatch
    - Send a prompt beginning with '!intake Director is Sarah, wrap time is 1900, camera is RED V-Raptor'.
    - Verify '!intake' is intercepted, prompt is cleaned, system directive prompt is injected.
    """
    raw_prompt = "!intake Director is Sarah, wrap time is 1900, camera is RED V-Raptor"

    # Test parser behavior
    clean_text, set_dirs, has_flush, has_intake, bootstrap_pack = InlineDirectiveParser.parse_and_clean_directives(raw_prompt)

    assert has_intake is True
    assert "!intake" not in clean_text
    assert "Director is Sarah" in clean_text

    # Test full proxy endpoint dispatch
    payload = {
        "model": "nostra-fast",
        "messages": [
            {"role": "user", "content": raw_prompt}
        ],
        "stream": False,
        "entity_id": "MadBrad-Intake-Directive-Test"
    }

    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    res_data = response.json()
    assert "choices" in res_data
    content = res_data["choices"][0]["message"]["content"]
    assert "[DUME_INTAKE_PROTOCOL]" in content or "Grounded context" in content


def test_context_flush_after_intake(client):
    """
    Acceptance Test 3: test_context_flush_after_intake
    - Add turns to conversational scratchpad buffer.
    - Execute batch intake commit with flush_scratchpad=True.
    - Verify conversational scratchpad memory is cleared while LMDB active registers remain intact.
    """
    entity_name = "MadBrad-Flush-Test-01"
    canonical_uuid = normalize_entity_id(entity_name)

    # 1. Add turn entries to scratchpad
    session_dispatcher.context_manager.add_turn(
        entity_id=canonical_uuid,
        user_text="Turn 1: Call sheet setup",
        agent_text="Acknowledged call sheet."
    )
    session_dispatcher.context_manager.add_turn(
        entity_id=canonical_uuid,
        user_text="Turn 2: Add camera details",
        agent_text="Camera set to RED V-Raptor."
    )

    summary_before = session_dispatcher.context_manager.get_scratchpad_summary(canonical_uuid)
    assert summary_before["active_turns"] == 2

    # 2. Run batch commit with flush_scratchpad=True
    payload = {
        "entity_id": entity_name,
        "registers": {
            "FLUSH_TEST_STATUS": "ACTIVE",
            "CAMERA_READY": True
        },
        "flush_scratchpad": True
    }

    response = client.post("/v1/dume/state/batch", json=payload)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["flushed_scratchpad"] is True

    # 3. Verify scratchpad is now empty (0 active turns)
    summary_after = session_dispatcher.context_manager.get_scratchpad_summary(canonical_uuid)
    assert summary_after["active_turns"] == 0

    # 4. Verify LMDB state registers persist despite scratchpad flush
    active_recs = memory_engine.get_all_active_registers(hex_to_uuid_bytes(canonical_uuid))
    assert len(active_recs) >= 2


def test_extraction_protocol_protection():
    """
    Rule 1 Verification: Protocol Protection
    Ignore ':' when preceded by http or https so URLs remain intact as single values.
    """
    from dume.scribe.ingest import extract_key_value_pairs

    doc = "EDITOR_URL = http://localhost:8070/editor\nAPI_SERVER: https://api.dumedb.local/v1/health"
    extracted = extract_key_value_pairs(doc)

    assert "EDITOR_URL" in extracted
    assert extracted["EDITOR_URL"] == "http://localhost:8070/editor"

    assert "API_SERVER" in extracted
    assert extracted["API_SERVER"] == "https://api.dumedb.local/v1/health"


def test_extraction_markdown_table_sanitization():
    """
    Rule 2 Verification: Markdown Table Sanitization
    Strip leading/trailing '|' delimiters and ignore markdown headers (#, ##) and separator rows.
    """
    from dume.scribe.ingest import extract_key_value_pairs

    doc = """# Production Roadmap
## Sprint Summary
| Feature | Status |
| :--- | :--- |
| PROJECT_STATUS | PHASE_2_TESTING |
| CAMERA_MODEL | RED V-Raptor |
"""
    extracted = extract_key_value_pairs(doc)

    assert "PROJECT_STATUS" in extracted
    assert extracted["PROJECT_STATUS"] == "PHASE_2_TESTING"

    assert "CAMERA_MODEL" in extracted
    assert extracted["CAMERA_MODEL"] == "RED V-Raptor"

    assert "#" not in extracted
    assert "Sprint Summary" not in extracted


def test_extraction_canonical_key_minting(client):
    """
    Rule 3 Verification: Canonical Key Minting
    Ensure extracted keys conform strictly to uppercase alphanumeric snake_case (^[A-Z0-9_]{3,32}$),
    rejecting conversational fragments like OVERWHELMED.
    """
    from dume.scribe.ingest import is_canonical_key, extract_key_value_pairs

    # Test key format validation
    assert is_canonical_key("PROJECT_STATUS") is True
    assert is_canonical_key("CAMERA_MODEL") is True
    assert is_canonical_key("OVERWHELMED") is False  # Rejected conversational noise
    assert is_canonical_key("A") is False            # Rejected too short (< 3 chars)
    assert is_canonical_key("THIS_KEY_IS_WAY_TOO_LONG_FOR_THE_THIRTY_TWO_CHARACTER_LIMIT") is False

    # Test extraction filtering
    doc = "OVERWHELMED = true\nPROJECT_STATUS = PHASE_2_TESTING\nA = 1"
    extracted = extract_key_value_pairs(doc)

    assert "PROJECT_STATUS" in extracted
    assert "OVERWHELMED" not in extracted
    assert "A" not in extracted

    # Test batch commit rejection of invalid keys
    payload = {
        "entity_id": "MadBrad-Canonical-Test",
        "registers": {
            "OVERWHELMED": "noise_value",
            "VALID_KEY": "valid_value"
        }
    }
    response = client.post("/v1/dume/state/batch", json=payload)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["committed_count"] == 1
    assert res_data["records"][0]["opcode_name"] == "VALID_KEY"


def test_extraction_markdown_table_header_skipping():
    """
    Rule 2 Refinement Verification: Skip Markdown Table Header Row.
    When parsing markdown tables, skip the very first row if it is followed by an alignment separator line
    (e.g. | :--- | :--- | or |---|---|).
    """
    from dume.scribe.ingest import extract_key_value_pairs

    doc = """
| Service | Endpoint |
| :--- | :--- |
| ENGINE_CORE | https://developumaiengine.com |
| PAGE_MANAGER_URL | http://localhost:8070/editor |
"""

    extracted = extract_key_value_pairs(doc)

    assert "SERVICE" not in extracted
    assert "ENGINE_CORE" in extracted
    assert extracted["ENGINE_CORE"] == "https://developumaiengine.com"
    assert "PAGE_MANAGER_URL" in extracted
    assert extracted["PAGE_MANAGER_URL"] == "http://localhost:8070/editor"


