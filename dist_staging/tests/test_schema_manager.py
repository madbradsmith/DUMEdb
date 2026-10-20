import pytest
from fastapi.testclient import TestClient
from dume.server.app import app, schema_dict
from dume.schema.dictionary import OpcodeSpec


@pytest.fixture
def client():
    return TestClient(app)


def test_preset_pack_listing(client):
    """GET /api/schema/packs lists available domain packs."""
    response = client.get("/api/schema/packs")
    assert response.status_code == 200
    data = response.json()
    assert "packs" in data
    pack_names = [p["name"] for p in data["packs"]]
    assert "film_production" in pack_names
    assert "software_dev" in pack_names
    assert "research_writing" in pack_names
    assert "strategy_admin" in pack_names


def test_preset_pack_loading_and_idempotency(client):
    """POST /api/schema/packs/load merges definitions without duplicates or wiping registers."""
    # 1. Load film_production pack
    resp = client.post("/api/schema/packs/load", json={"pack_name": "film_production"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["pack_name"] == "film_production"
    assert data["loaded_count"] == 6

    # Verify opcode 1100 (WORKSPACE_ROLE) exists in active schema dictionary
    spec = schema_dict.get_spec(1100)
    assert spec is not None
    assert spec.name == "WORKSPACE_ROLE"
    assert spec.data_type == "ENUM"

    # 2. Idempotency check: load film_production again
    resp2 = client.post("/api/schema/packs/load", json={"pack_name": "film_production"})
    assert resp2.status_code == 200
    assert resp2.json()["success"] is True

    # 3. Verify loading status in GET /api/schema/packs
    packs_resp = client.get("/api/schema/packs")
    packs_data = packs_resp.json()
    film_pack = next(p for p in packs_data["packs"] if p["name"] == "film_production")
    assert film_pack["is_loaded"] is True


def test_manual_custom_minting(client):
    """POST /api/schema/custom mints a novel custom opcode in the 3xxx range."""
    resp = client.post("/api/schema/custom", json={
        "name": "TEST_CAMPAIGN_BUDGET",
        "data_type": "INT",
        "description": "Test custom budget opcode",
        "unit": "USD"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    spec_data = data["spec"]
    assert spec_data["opcode"] >= 3001
    assert spec_data["opcode"] <= 3999
    assert spec_data["name"] == "TEST_CAMPAIGN_BUDGET"
    assert spec_data["unit"] == "USD"
    assert spec_data["is_auto"] is False


def test_auto_opcode_promotion(client):
    """POST /api/schema/promote re-classifies a 2xxx auto opcode into permanent registry."""
    # Register temporary auto opcode
    auto_spec = OpcodeSpec(
        opcode=2099,
        name="TEST_AUTO_PROJECT_NAME",
        description="Auto discovered project name",
        data_type="STRING_REF",
        is_auto=True
    )
    schema_dict.register_opcode(auto_spec, persist=False, is_custom=False)
    assert schema_dict.get_spec(2099).is_auto is True

    # Promote via API route
    resp = client.post("/api/schema/promote", json={"opcode": 2099})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["spec"]["is_auto"] is False
    assert schema_dict.get_spec(2099).is_auto is False


def test_schema_export(client):
    """GET /api/schema/export downloads full active schema dictionary as JSON."""
    resp = client.get("/api/schema/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json"
    assert "attachment" in resp.headers.get("content-disposition", "")
    data = resp.json()
    assert "version" in data
    assert "opcodes" in data
    assert isinstance(data["opcodes"], list)
    assert len(data["opcodes"]) > 0
