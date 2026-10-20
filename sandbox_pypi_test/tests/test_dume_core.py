import tempfile
import pytest
from pathlib import Path

from dume.core.record import (
    UnitRecord, RECORD_SIZE_BYTES, generate_uuidv7_bytes, uuid_to_hex, FLAG_ACTIVE
)
from dume.schema.dictionary import SchemaDictionary, OpcodeSpec
from dume.storage.lmdb_engine import DUMEMemoryEngine
from dume.ingestion.parser import ConstrainedIngestionEngine, IngestionError
from dume.inference.grounded_engine import GroundedInferenceEngine


def test_32_byte_record_pack_unpack():
    entity_bytes = generate_uuidv7_bytes()
    opcode = 1001
    value = 25000
    timestamp = 1700000000
    flags = FLAG_ACTIVE

    record = UnitRecord(
        entity_id=entity_bytes,
        opcode=opcode,
        value=value,
        timestamp=timestamp,
        flags=flags
    )

    packed = record.pack()
    assert len(packed) == 32, f"Packed record must be exactly 32 bytes, got {len(packed)}"

    unpacked = UnitRecord.unpack(packed)
    assert unpacked.entity_id == entity_bytes
    assert unpacked.opcode == opcode
    assert unpacked.value == value
    assert unpacked.timestamp == timestamp
    assert unpacked.flags == flags
    assert unpacked.is_active is True


def test_uuidv7_chronological_ordering():
    uuid1 = generate_uuidv7_bytes(ts_ms=1000)
    uuid2 = generate_uuidv7_bytes(ts_ms=2000)
    assert uuid1 < uuid2


def test_float_value_packing():
    entity_bytes = generate_uuidv7_bytes()
    rec = UnitRecord.create(
        entity_id=entity_bytes,
        opcode=1005,
        value=23.75,
        is_active=True
    )
    assert rec.is_float_value is True
    assert abs(rec.float_value - 23.75) < 1e-6

    packed = rec.pack()
    unpacked = UnitRecord.unpack(packed)
    assert abs(unpacked.float_value - 23.75) < 1e-6


def test_schema_dictionary_decoding():
    schema = SchemaDictionary()
    entity_bytes = generate_uuidv7_bytes()
    
    rec = UnitRecord.create(
        entity_id=entity_bytes,
        opcode=1003, # ACCOUNT_TIER
        value=2,     # PRO
        is_active=True
    )

    decoded = schema.decode_record(rec)
    assert decoded["opcode_name"] == "ACCOUNT_TIER"
    assert decoded["human_value"] == "PRO"
    assert decoded["flags"]["active"] is True


def test_lmdb_storage_engine_o1_lookup():
    with tempfile.TemporaryDirectory() as tmpdir:
        with DUMEMemoryEngine(db_path=tmpdir) as engine:
            entity_bytes = generate_uuidv7_bytes()
            
            rec1 = UnitRecord.create(entity_id=entity_bytes, opcode=1001, value=1)
            rec2 = UnitRecord.create(entity_id=entity_bytes, opcode=1002, value=1)

            engine.put_record(rec1)
            engine.put_record(rec2)

            fetched1 = engine.get_active_record(entity_bytes, 1001)
            assert fetched1 is not None
            assert fetched1.value == 1

            all_regs = engine.get_all_active_registers(entity_bytes)
            assert len(all_regs) == 2

            # Test Tombstone
            engine.tombstone_register(entity_bytes, 1001)
            tombstoned = engine.get_active_record(entity_bytes, 1001)
            assert tombstoned is None


def test_constrained_ingestion_validation():
    schema = SchemaDictionary()
    parser = ConstrainedIngestionEngine(schema)
    entity_bytes = generate_uuidv7_bytes()

    # Valid mutation
    rec, _ = parser.validate_and_parse(entity_bytes, "UI_THEME", "DARK")
    assert rec.opcode == 1002
    assert rec.value == 1

    # Invalid opcode
    with pytest.raises(IngestionError):
        parser.validate_and_parse(entity_bytes, "NON_EXISTENT_OPCODE", "TEST")

    # Invalid enum
    with pytest.raises(IngestionError):
        parser.validate_and_parse(entity_bytes, "UI_THEME", "INVALID_THEME_NAME")


def test_grounded_inference_context_injection():
    with tempfile.TemporaryDirectory() as tmpdir:
        with DUMEMemoryEngine(db_path=tmpdir) as engine:
            schema = SchemaDictionary()
            parser = ConstrainedIngestionEngine(schema)
            infer = GroundedInferenceEngine(engine, schema)

            entity_bytes = generate_uuidv7_bytes()
            rec1, _ = parser.validate_and_parse(entity_bytes, 1001, "en-US")
            rec2, _ = parser.validate_and_parse(entity_bytes, 1003, "PRO")
            
            engine.put_record(rec1)
            engine.put_record(rec2)

            result = infer.generate(entity_bytes, "What is my account tier?")
            assert "[DUME_STATE" in result["register_context"]
            assert "USER_LOCALE=en-US" in result["register_context"]
            assert "ACCOUNT_TIER=PRO" in result["register_context"]
            assert result["register_token_count"] <= 50
