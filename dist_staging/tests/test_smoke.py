import tempfile
import pytest
import os
from pathlib import Path

from dume.core.record import UnitRecord, uuid_to_hex
from dume.core.seed import seed_starter_profile
from dume.storage.lmdb_engine import DUMEMemoryEngine
from dume.schema.dictionary import SchemaDictionary
from dume.ingestion.parser import StateParser, IngestionError
from dume.inference.grounded_engine import GroundedInferenceEngine


def test_cold_boot_seeding():
    """Verify cold boot seeding creates 4 starter registers with canonical UUID."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with DUMEMemoryEngine(db_path=tmpdir) as engine:
            schema = SchemaDictionary()
            seed_starter_profile(engine, schema)

            entity_ids = engine.get_all_entity_ids()
            assert len(entity_ids) == 1
            
            records = engine.get_all_active_registers(entity_ids[0])
            assert len(records) == 4

            decoded = [schema.decode_record(r, resolver=engine.get_payload_text) for r in records]
            names = {d["opcode_name"] for d in decoded}
            assert "DUME_COMMUNITY_EDITION_V1_0" in names
            assert "PROJECT_STATUS" in names
            assert "WORKSPACE_ROLE" in names
            assert "FOCUS_MODE" in names


def test_type_round_trips():
    """Verify INT, FLOAT, BOOL, ENUM, and STRING_REF intake, storage, retrieval, and decoding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with DUMEMemoryEngine(db_path=tmpdir) as engine:
            schema = SchemaDictionary()
            parser = StateParser(schema)
            entity_id = "SmokeTest-Entity-01"

            # 1. INT
            rec_int, _ = parser.parse_mutation(entity_id, "MAX_TOKENS_PER_TURN", 4096)
            engine.put_record(rec_int)
            
            # 2. FLOAT
            rec_float, _ = parser.parse_mutation(entity_id, "TEMPERATURE_PREFERENCE", 0.75)
            engine.put_record(rec_float)

            # 3. BOOL
            rec_bool, _ = parser.parse_mutation(entity_id, "AUTO_SAVE_ENABLED", True)
            engine.put_record(rec_bool)

            # 4. ENUM
            rec_enum, _ = parser.parse_mutation(entity_id, "PROJECT_STATUS", "DEPLOYED")
            engine.put_record(rec_enum)

            # 5. STRING_REF
            rec_str, payload_bytes = parser.parse_mutation(entity_id, "CURRENT_BRANCH", "feature/multimodal-intake")
            engine.put_record(rec_str, payload_bytes=payload_bytes)

            records = engine.get_all_active_registers(entity_id)
            assert len(records) == 5

            decoded_map = {}
            for r in records:
                d = schema.decode_record(r, resolver=engine.get_payload_text)
                decoded_map[d["opcode_name"]] = d["human_value"]

            assert decoded_map["MAX_TOKENS_PER_TURN"] == 4096
            assert pytest.approx(decoded_map["TEMPERATURE_PREFERENCE"], 0.01) == 0.75
            assert decoded_map["AUTO_SAVE_ENABLED"] is True
            assert decoded_map["PROJECT_STATUS"] == "DEPLOYED"
            assert decoded_map["CURRENT_BRANCH"] == "feature/multimodal-intake"


def test_history_ordering_newest_first():
    """Verify get_history returns chronological audit log in reverse order (newest first)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with DUMEMemoryEngine(db_path=tmpdir) as engine:
            schema = SchemaDictionary()
            parser = StateParser(schema)
            entity_id = "HistoryOrderTest-01"

            rec1, _ = parser.parse_mutation(entity_id, "MAX_TOKENS_PER_TURN", 1000)
            engine.put_record(rec1)

            rec2, _ = parser.parse_mutation(entity_id, "MAX_TOKENS_PER_TURN", 2000)
            engine.put_record(rec2)

            rec3, _ = parser.parse_mutation(entity_id, "MAX_TOKENS_PER_TURN", 3000)
            engine.put_record(rec3)

            history = engine.get_history(entity_id, limit=3)
            assert len(history) == 3
            # Newest should be last written value (3000)
            assert history[0].value == 3000


def test_proxy_dume_state_context_injection():
    """Verify GroundedInferenceEngine prompt construction includes [DUME_STATE ...] context prefix."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with DUMEMemoryEngine(db_path=tmpdir) as engine:
            schema = SchemaDictionary()
            parser = StateParser(schema)
            entity_id = "ContextInject-01"

            rec, payload = parser.parse_mutation(entity_id, "CURRENT_BRANCH", "main")
            engine.put_record(rec, payload_bytes=payload)

            grounded = GroundedInferenceEngine(engine, schema)
            ctx = grounded.build_register_context(entity_id)

            assert "[DUME_STATE" in ctx
            assert "CURRENT_BRANCH=main" in ctx
            assert "[/DUME_STATE]" in ctx


def test_illegal_enum_validation():
    """Verify illegal enum values are rejected with IngestionError."""
    schema = SchemaDictionary()
    parser = StateParser(schema)

    with pytest.raises(IngestionError) as exc_info:
        parser.parse_mutation("TestEntity", "PROJECT_STATUS", "INVALID_STATUS_XYZ")
    assert "Invalid enum string" in str(exc_info.value)
