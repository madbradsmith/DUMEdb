import pytest
from pathlib import Path
from dume.storage.lmdb_engine import DUMEMemoryEngine
from dume.schema.dictionary import SchemaDictionary
from dume.scribe.committer import ScribeCommitter
from dume.scribe.worker import ScribeWorker
from dume.session.dispatcher import SessionDispatcher, TurnPayload
from dume.inference.grounded_engine import GroundedInferenceEngine
from dume.server.app import normalize_entity_id


def test_auto_schema_discovery_and_commit(tmp_path):
    """
    Acceptance Criteria 1: test_auto_schema_discovery_and_commit
    1. Send simulated turn: "My primary camera lens is a 50mm prime."
    2. Scribe detects novel domain, registers CAMERA_LENS_FOCAL_LENGTH_MM (Type INT), and persists to disk.
    3. Verify that a valid 32-byte binary record is written to LMDB under newly minted opcode with value 50.
    """
    db_dir = tmp_path / "lmdb_auto_disc"
    json_path = tmp_path / "registered_schemas.json"

    engine = DUMEMemoryEngine(db_path=db_dir)
    schema_dict = SchemaDictionary(storage_path=json_path)
    committer = ScribeCommitter(engine, schema_dict)
    grounded_engine = GroundedInferenceEngine(engine, schema_dict)
    dispatcher = SessionDispatcher(grounded_engine)
    worker = ScribeWorker(dispatcher, committer, schema_dict)

    raw_entity_id = "MadBrad-Camera-Test"
    canonical_uuid = normalize_entity_id(raw_entity_id)

    payload = TurnPayload(
        entity_id=canonical_uuid,
        user_text="My primary camera lens is a 50mm prime.",
        agent_text="Got it! Saved camera lens 50mm.",
        timestamp=1000000
    )

    # Execute Scribe processing
    committed_events = worker.process_turn(payload)

    # 1. Verify mutation committed
    assert len(committed_events) == 1
    event = committed_events[0]
    assert event["opcode_name"] == "CAMERA_LENS_FOCAL_LENGTH_MM"
    assert event["human_value"] == 50

    # 2. Verify schema spec was dynamically registered and marked is_auto=True
    minted_opcode = event["opcode"]
    spec = schema_dict.get_spec(minted_opcode)
    assert spec is not None
    assert spec.name == "CAMERA_LENS_FOCAL_LENGTH_MM"
    assert spec.is_auto is True
    assert spec.data_type == "INT"

    # 3. Verify valid 32-byte UnitRecord written to LMDB
    record = engine.get_active_record(canonical_uuid, minted_opcode)
    assert record is not None
    assert record.value == 50
    assert record.opcode == minted_opcode

    engine.close()


def test_auto_schema_deduplication(tmp_path):
    """
    Acceptance Criteria 2: test_auto_schema_deduplication
    1. Send initial turn: "My primary camera lens is a 50mm prime."
    2. Send subsequent turn variation: "Set my camera lens to 35mm."
    3. Scribe recognizes existing opcode CAMERA_LENS_FOCAL_LENGTH_MM and mutates active register without minting duplicate opcode.
    """
    db_dir = tmp_path / "lmdb_auto_dedup"
    json_path = tmp_path / "registered_schemas.json"

    engine = DUMEMemoryEngine(db_path=db_dir)
    schema_dict = SchemaDictionary(storage_path=json_path)
    committer = ScribeCommitter(engine, schema_dict)
    grounded_engine = GroundedInferenceEngine(engine, schema_dict)
    dispatcher = SessionDispatcher(grounded_engine)
    worker = ScribeWorker(dispatcher, committer, schema_dict)

    raw_entity_id = "MadBrad-Camera-Dedup"
    canonical_uuid = normalize_entity_id(raw_entity_id)

    # Turn 1: Discover & Mint
    payload1 = TurnPayload(
        entity_id=canonical_uuid,
        user_text="My primary camera lens is a 50mm prime.",
        agent_text="Noted 50mm lens.",
        timestamp=1000000
    )
    events1 = worker.process_turn(payload1)
    assert len(events1) == 1
    opcode1 = events1[0]["opcode"]

    opcodes_count_after_turn1 = len(schema_dict.get_all_specs())

    # Turn 2: Subsequent variation using same domain
    payload2 = TurnPayload(
        entity_id=canonical_uuid,
        user_text="Set my camera lens to 35mm.",
        agent_text="Updated camera lens to 35mm.",
        timestamp=1000005
    )
    events2 = worker.process_turn(payload2)
    assert len(events2) == 1
    opcode2 = events2[0]["opcode"]

    # 1. Opcode ID must be IDENTICAL (no duplicate opcode minted!)
    assert opcode1 == opcode2

    # 2. Total schema opcode count must NOT increase
    opcodes_count_after_turn2 = len(schema_dict.get_all_specs())
    assert opcodes_count_after_turn2 == opcodes_count_after_turn1

    # 3. Active register in LMDB updated to 35
    record = engine.get_active_record(canonical_uuid, opcode1)
    assert record is not None
    assert record.value == 35

    engine.close()
