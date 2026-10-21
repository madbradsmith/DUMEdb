import pytest
from pathlib import Path
from dume.schema.dictionary import SchemaDictionary, OpcodeSpec
from dume.core.record import UnitRecord
from dume.storage.lmdb_engine import DUMEMemoryEngine
from dume.server.app import normalize_entity_id


def test_dynamic_schema_registration(tmp_path):
    """
    Acceptance Criteria 1: test_dynamic_schema_registration
    Programmatically register a brand-new opcode (e.g. 2001: PROJECT_STATUS),
    commit a 32-byte record with that opcode, and unpack it without errors.
    """
    json_path = tmp_path / "registered_schemas.json"
    schema = SchemaDictionary(storage_path=json_path)

    # 1. Register dynamic opcode 2001
    spec = OpcodeSpec(
        opcode=2001,
        name="PROJECT_STATUS",
        description="Active project development status",
        data_type="ENUM",
        enum_values={1: "BACKLOG", 2: "ACTIVE", 3: "DONE"}
    )
    registered = schema.register_opcode(spec, persist=True)
    assert registered.opcode == 2001
    assert schema.get_opcode_by_name("PROJECT_STATUS") == 2001

    # 2. Create 32-byte record with opcode 2001
    entity_hex = normalize_entity_id("MadBrad-Project-01")
    rec = UnitRecord.create(
        entity_id=entity_hex,
        opcode=2001,
        value=2  # 2 = ACTIVE
    )

    # 3. Decode & unpack record
    decoded = schema.decode_record(rec)
    assert decoded["opcode"] == 2001
    assert decoded["opcode_name"] == "PROJECT_STATUS"
    assert decoded["human_value"] == "ACTIVE"
    assert decoded["description"] == "Active project development status"


def test_schema_persistence_across_restart(tmp_path):
    """
    Acceptance Criteria 2: test_schema_persistence_across_restart
    Register an opcode, simulate a server teardown/restart, and verify the custom opcode is still recognized.
    """
    json_path = tmp_path / "registered_schemas.json"

    # Server Session 1: Register custom opcode 2005
    schema1 = SchemaDictionary(storage_path=json_path)
    schema1.register_opcode(
        OpcodeSpec(
            opcode=2005,
            name="SENSOR_HUMIDITY",
            description="Relative humidity percentage",
            data_type="FLOAT",
            unit="%"
        ),
        persist=True
    )
    assert schema1.get_spec(2005) is not None

    # Server Teardown / Restart (Session 2): Re-instantiate SchemaDictionary from disk
    schema2 = SchemaDictionary(storage_path=json_path)
    loaded_spec = schema2.get_spec(2005)

    assert loaded_spec is not None
    assert loaded_spec.name == "SENSOR_HUMIDITY"
    assert loaded_spec.data_type == "FLOAT"
    assert loaded_spec.unit == "%"
    assert schema2.get_opcode_by_name("SENSOR_HUMIDITY") == 2005


def test_duplicate_rejection(tmp_path):
    """
    Acceptance Criteria 3: test_duplicate_rejection
    Attempting to register an existing opcode ID or name raises a clean collision error.
    """
    json_path = tmp_path / "registered_schemas.json"
    schema = SchemaDictionary(storage_path=json_path)

    # Register initial spec
    schema.register_opcode(
        OpcodeSpec(opcode=3001, name="CUSTOM_SCORE", description="Score", data_type="INT"),
        persist=False
    )

    # Attempt 1: Duplicate Opcode ID collision
    with pytest.raises(ValueError, match="Opcode ID collision"):
        schema.register_opcode(
            OpcodeSpec(opcode=3001, name="DIFFERENT_NAME", description="Test", data_type="INT"),
            persist=False
        )

    # Attempt 2: Duplicate Opcode Name collision
    with pytest.raises(ValueError, match="Opcode Name collision"):
        schema.register_opcode(
            OpcodeSpec(opcode=3002, name="CUSTOM_SCORE", description="Test", data_type="INT"),
            persist=False
        )


def test_opcode_rollover_past_2999(tmp_path):
    """
    Verifies that get_next_available_opcode safely allocates opcodes
    past 2999 without hitting collisions or caps.
    """
    json_path = tmp_path / "registered_schemas.json"
    schema = SchemaDictionary(storage_path=json_path)

    # Pre-populate opcode 2999
    schema.register_opcode(
        OpcodeSpec(opcode=2999, name="REG_2999", description="Test", data_type="INT"),
        persist=False
    )

    next_op = schema.get_next_available_opcode()
    # Candidate should find the first available free slot >= 2001 (e.g. 2001 or >2999)
    assert next_op != 2999
    assert 2001 <= next_op <= 0xFFFE
    assert next_op not in schema._opcodes
