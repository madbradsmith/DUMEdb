import os
os.environ["DUME_TESTING"] = "1"

import sys
import tempfile
import socket
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dume.storage.lmdb_engine import DUMEMemoryEngine
from dume.schema.dictionary import SchemaDictionary
from dume.core.record import UnitRecord, uuid_to_hex, hex_to_uuid_bytes
from dume.scribe.ingest import BatchIngestionEngine, extract_key_value_pairs
from dume.server.app import app, normalize_entity_id


def test_cold_start_fresh_environment():
    """
    1. Cold Start in Fresh Environment:
    Spin up storage and schema engine pointing to a brand-new empty temporary directory.
    Assert LMDB and schema dictionary initialize cleanly without FileNotFoundError or unhandled exceptions.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / "lmdb_cold_start"
        assert not temp_path.exists()

        # Initialize engines on empty path
        engine = DUMEMemoryEngine(db_path=temp_path)
        schema_dict = SchemaDictionary()

        assert engine.env is not None
        assert schema_dict.get_spec(2001) is not None

        # Verify operational capability on cold state
        canonical_uuid = normalize_entity_id("ColdStartEntity")
        canonical_uuid_bytes = hex_to_uuid_bytes(canonical_uuid)

        rec = UnitRecord.create(
            entity_id=canonical_uuid_bytes,
            opcode=2001,
            value=1
        )
        assert engine.put_record(rec) is True

        active = engine.get_all_active_registers(canonical_uuid)
        assert len(active) == 1
        assert active[0].opcode == 2001

        engine.close()


def test_port_conflict_and_graceful_teardown():
    """
    2. Port Conflict & Graceful Teardown:
    Verify that binding a socket on an already-bound port (e.g. port 8090) reports a clear error.
    Verify that closing LMDB engine leaves no unclosed handles or lock errors on immediate re-instantiation.
    """
    # Test socket port 8090 conflict error reporting
    conflict_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        conflict_sock.bind(("127.0.0.1", 8090))
        conflict_sock.listen(1)
        # Attempt binding 2nd socket to same port
        sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        with pytest.raises(OSError) as exc_info:
            sock2.bind(("127.0.0.1", 8090))
        err_msg = str(exc_info.value)
        assert "10048" in err_msg or "in use" in err_msg.lower() or "address" in err_msg.lower() or "permitted" in err_msg.lower()
        sock2.close()
    except OSError as err:
        # Port 8090 is already bound by live uvicorn process — verifies port conflict error
        err_msg = str(err)
        assert "10048" in err_msg or "in use" in err_msg.lower() or "address" in err_msg.lower() or "permitted" in err_msg.lower()
    finally:
        try:
            conflict_sock.close()
        except Exception:
            pass

    # Test LMDB graceful teardown & immediate re-instantiation
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / "lmdb_teardown"
        
        # Instantiate & populate
        engine1 = DUMEMemoryEngine(db_path=temp_path)
        canonical_bytes = hex_to_uuid_bytes(normalize_entity_id("TeardownEntity"))
        rec = UnitRecord.create(entity_id=canonical_bytes, opcode=2001, value=100)
        engine1.put_record(rec)
        
        # Close engine 1
        engine1.close()

        # Immediate re-instantiation on same directory
        engine2 = DUMEMemoryEngine(db_path=temp_path)
        active_recs = engine2.get_all_active_registers(normalize_entity_id("TeardownEntity"))
        assert len(active_recs) == 1
        assert active_recs[0].opcode == 2001
        engine2.close()


def test_entity_boundary_isolation():
    """
    3. Entity Boundary Isolation:
    Commit distinct registers to Entity_Alpha and Entity_Beta.
    Verify that reading Entity_Beta returns zero keys from Entity_Alpha, confirming strict memory partitioning across headers/query params.
    """
    client = TestClient(app)

    # Commit register to Entity_Alpha via X-Entity-ID header
    res_alpha = client.post(
        "/v1/dume/state/batch",
        json={"registers": {"ALPHA_SECRET": "AlphaValue123"}},
        headers={"X-Entity-ID": "Entity_Alpha"}
    )
    assert res_alpha.status_code == 200

    # Commit register to Entity_Beta via ?entity_id query parameter
    res_beta = client.post(
        "/v1/dume/state/batch?entity_id=Entity_Beta",
        json={"registers": {"BETA_SECRET": "BetaValue456"}}
    )
    assert res_beta.status_code == 200

    # Read Entity_Beta active registers via inspector API
    res_beta_get = client.get("/api/registers/Entity_Beta")
    assert res_beta_get.status_code == 200
    beta_json = res_beta_get.json()
    beta_op_names = [r["opcode_name"] for r in beta_json.get("registers", [])]

    # Verify Beta contains BETA_SECRET and ZERO keys from Entity_Alpha
    assert "BETA_SECRET" in beta_op_names
    assert "ALPHA_SECRET" not in beta_op_names

    # Read Entity_Alpha active registers via inspector API
    res_alpha_get = client.get("/api/registers/Entity_Alpha")
    assert res_alpha_get.status_code == 200
    alpha_json = res_alpha_get.json()
    alpha_op_names = [r["opcode_name"] for r in alpha_json.get("registers", [])]

    # Verify Alpha contains ALPHA_SECRET and ZERO keys from Entity_Beta
    assert "ALPHA_SECRET" in alpha_op_names
    assert "BETA_SECRET" not in alpha_op_names


def test_openai_endpoint_compatibility():
    """
    4. OpenAI Endpoint Compatibility (/v1/models & Streaming):
    - GET /v1/models returns standard 200 OK JSON list.
    - POST /v1/chat/completions with stream=true confirms SSE streaming chunks pass through uncorrupted.
    """
    client = TestClient(app)

    # 1. GET /v1/models
    res_models = client.get("/v1/models")
    assert res_models.status_code == 200
    models_data = res_models.json()
    assert models_data.get("object") == "list"
    assert isinstance(models_data.get("data"), list)
    assert len(models_data["data"]) > 0
    assert "id" in models_data["data"][0]

    # 2. POST /v1/chat/completions with stream=true
    stream_payload = {
        "model": "qwen2.5:0.5b",
        "messages": [{"role": "user", "content": "Hello DUME"}],
        "stream": True
    }
    res_stream = client.post("/v1/chat/completions", json=stream_payload)
    assert res_stream.status_code == 200
    assert "text/event-stream" in res_stream.headers.get("content-type", "")

    stream_content = res_stream.text
    assert "data:" in stream_content
    assert "[DONE]" in stream_content


def test_complex_quoted_document_intake():
    """
    5. Complex / Quoted Document Intake:
    Run an intake payload containing escaped strings, JSON blobs, and code syntax:
    BUILD_CMD = "npm run build --prefix ./client"
    CONFIG_JSON = {"debug": true, "timeout": 30}
    Assert that the parser preserves inner quotes and braces without throwing regex or syntax errors.
    """
    complex_payload = """
    BUILD_CMD = "npm run build --prefix ./client"

    CONFIG_JSON = {"debug": true, "timeout": 30}
    """

    extracted = extract_key_value_pairs(complex_payload)

    assert "BUILD_CMD" in extracted, f"Expected BUILD_CMD in extracted keys: {extracted}"
    assert extracted["BUILD_CMD"] == "npm run build --prefix ./client", f"Expected clean command string, got {extracted.get('BUILD_CMD')}"

    assert "CONFIG_JSON" in extracted, f"Expected CONFIG_JSON in extracted keys: {extracted}"
    assert extracted["CONFIG_JSON"] == '{"debug": true, "timeout": 30}', f"Expected preserved JSON blob, got {extracted.get('CONFIG_JSON')}"
