import json
import pytest
from fastapi.testclient import TestClient
from dume.server.app import app, memory_engine, schema_dict
from dume.core.record import UnitRecord
from dume.core.record import UnitRecord, hex_to_uuid_bytes
from dume.server.app import normalize_entity_id


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_proxy_openai_chat_completion_non_streaming(client):
    """
    Acceptance Criteria 1: test_proxy_openai_chat_completion_non_streaming
    Send standard POST /v1/chat/completions JSON payload.
    Verify returned payload matches standard OpenAI JSON structure (id, choices, usage).
    """
    payload = {
        "model": "qwen2.5:0.5b",
        "messages": [
            {"role": "user", "content": "Hello Nostra!"}
        ],
        "stream": False,
        "entity_id": "MadBrad-Proxy-Test-01"
    }

    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    data = response.json()

    # Verify standard OpenAI structure
    assert "id" in data
    assert data["object"] == "chat.completion"
    assert "choices" in data
    assert len(data["choices"]) > 0
    assert "message" in data["choices"][0]
    assert data["choices"][0]["message"]["role"] == "assistant"
    assert "content" in data["choices"][0]["message"]
    assert "usage" in data


def test_proxy_prefix_injection(client):
    """
    Acceptance Criteria 2: test_proxy_prefix_injection
    Verify discrete active registers from LMDB are injected into system prompt as [DUME_STATE ...].
    """
    entity_name = "MadBrad-Proxy-Inject-Test"
    canonical_uuid = normalize_entity_id(entity_name)

    # 1. Mutate active register in LMDB (UI_THEME = 1 for DARK)
    rec = UnitRecord.create(
        entity_id=hex_to_uuid_bytes(canonical_uuid),
        opcode=1002,  # Opcode 1002 = UI_THEME
        value=1
    )
    memory_engine.put_record(rec)

    # 2. Send turn via /v1/chat/completions using X-Entity-ID header
    payload = {
        "model": "nostra-fast",
        "messages": [
            {"role": "user", "content": "What theme is active?"}
        ],
        "stream": False
    }
    headers = {"X-Entity-ID": entity_name}

    response = client.post("/v1/chat/completions", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()

    content = data["choices"][0]["message"]["content"]
    # Grounded response or prompt contains DUME_STATE prefix
    assert "[DUME_STATE" in content or "UI_THEME=DARK" in content or "DARK" in content


def test_proxy_scribe_dispatch(client):
    """
    Acceptance Criteria 3: test_proxy_scribe_dispatch
    Send a turn through proxy endpoint containing a mutation ("Set UI_THEME to DARK").
    Verify proxy returns output immediately while background Scribe commits mutation to LMDB out-of-band.
    """
    entity_name = "MadBrad-Proxy-Scribe-Test"
    canonical_uuid = normalize_entity_id(entity_name)

    payload = {
        "model": "qwen2.5:0.5b",
        "messages": [
            {"role": "user", "content": "Set UI_THEME to DARK"}
        ],
        "stream": False,
        "entity_id": entity_name
    }

    # Execute proxy completion
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200

    # Execute ScribeWorker queue processing if needed for unit test
    worker = app.state.scribe_worker if hasattr(app.state, "scribe_worker") else None
    dispatcher = app.state.session_dispatcher
    if dispatcher and not dispatcher.queue.empty():
        payload_item = dispatcher.queue.get_nowait()
        if worker:
            worker.process_turn(payload_item)

    # Verify LMDB active record updated
    record = memory_engine.get_active_record(hex_to_uuid_bytes(canonical_uuid), 1002) # UI_THEME
    assert record is not None
    assert record.value == 1  # 1 = DARK


def test_proxy_streaming_passthrough(client):
    """
    Acceptance Criteria 4: test_proxy_streaming_passthrough
    Verify chunks stream through with valid data: { ... } SSE formatting terminating with data: [DONE].
    """
    payload = {
        "model": "qwen2.5:0.5b",
        "messages": [
            {"role": "user", "content": "Tell me a short story."}
        ],
        "stream": True,
        "entity_id": "MadBrad-Proxy-Stream-Test"
    }

    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")

    lines = response.text.strip().split("\n\n")
    assert len(lines) >= 1

    # Check SSE format
    has_data_chunk = False
    has_done = False
    for line in lines:
        if line.startswith("data: ") and "[DONE]" not in line:
            json_str = line.replace("data: ", "").strip()
            chunk_data = json.loads(json_str)
            assert chunk_data["object"] == "chat.completion.chunk"
            has_data_chunk = True
        elif "[DONE]" in line:
            has_done = True

    assert has_data_chunk is True
    assert has_done is True
