import pytest
from dume.session.context_manager import BoundedBufferManager
from dume.inference.grounded_engine import GroundedInferenceEngine
from dume.schema.dictionary import SchemaDictionary
from dume.storage.lmdb_engine import DUMEMemoryEngine
from dume.core.record import UnitRecord


def test_sliding_window_eviction():
    """
    Acceptance Criteria 1: test_sliding_window_eviction
    Verify that after sending K + 1 turns, the first turn is evicted while the latest turn is appended.
    """
    manager = BoundedBufferManager(max_turns=4, max_tokens=2048, policy="SLIDING_WINDOW")
    entity_id = "test-entity-sliding"

    # Send 4 turns (Fill capacity)
    for i in range(1, 5):
        manager.add_turn(entity_id, f"User Turn {i}", f"Agent Response {i}")

    history = manager.get_bounded_history(entity_id)
    assert len(history) == 4
    assert history[0].user_text == "User Turn 1"
    assert history[3].user_text == "User Turn 4"

    # Send 5th turn (Exceed capacity K=4)
    manager.add_turn(entity_id, "User Turn 5", "Agent Response 5")

    history_after = manager.get_bounded_history(entity_id)
    assert len(history_after) == 4
    # Turn 1 evicted!
    assert history_after[0].user_text == "User Turn 2"
    assert history_after[3].user_text == "User Turn 5"


def test_state_persistence_across_flush(tmp_path):
    """
    Acceptance Criteria 2: test_state_persistence_across_flush
    1. Commit a register mutation (USER_THEME = 1 for Dark mode).
    2. Execute a full context flush (flush_session_scratchpad).
    3. Verify the next inference prompt still contains USER_THEME=Dark via [DUME_STATE] prefix.
    """
    from dume.server.app import normalize_entity_id

    db_dir = tmp_path / "lmdb_test_flush"
    engine = DUMEMemoryEngine(db_path=db_dir)
    schema_dict = SchemaDictionary()
    grounded_engine = GroundedInferenceEngine(engine, schema_dict)
    manager = BoundedBufferManager(max_turns=4, max_tokens=2048)

    raw_entity_id = "MadBrad-Nostra-FlushTest"
    canonical_uuid = normalize_entity_id(raw_entity_id)

    # 1. Commit mutation (Opcode 1002 = UI_THEME, value 1 = DARK)
    rec = UnitRecord.create(
        entity_id=canonical_uuid,
        opcode=1002,  # Opcode 1002 = UI_THEME
        value=1
    )
    engine.put_record(rec)

    # Populate scratchpad with turns
    manager.add_turn(canonical_uuid, "Hello", "Hi there")
    manager.add_turn(canonical_uuid, "What is my theme?", "DARK mode")

    assert len(manager.get_bounded_history(canonical_uuid)) == 2

    # 2. Execute full context flush
    manager.flush_session_scratchpad(canonical_uuid)
    assert len(manager.get_bounded_history(canonical_uuid)) == 0

    # 3. Verify next inference prompt STILL contains active register via DUME_STATE prefix!
    prompt_after_flush = grounded_engine.format_grounded_prompt(
        canonical_uuid,
        "Next turn after flush",
        manager.get_bounded_history(canonical_uuid)
    )

    assert "[DUME_STATE" in prompt_after_flush
    assert "UI_THEME=DARK" in prompt_after_flush
    assert "User: Next turn after flush" in prompt_after_flush

    engine.close()


def test_token_ceiling_invariance():
    """
    Acceptance Criteria 3: test_token_ceiling_invariance
    Verify prompt length never exceeds the configured token threshold regardless of turn count (across 50 simulated turns).
    """
    manager = BoundedBufferManager(max_turns=4, max_tokens=500, policy="SLIDING_WINDOW")
    entity_id = "test-entity-token-ceiling"

    # Execute 50 simulated turns
    for i in range(1, 51):
        long_user_text = f"User Turn {i}: " + ("text " * 30)
        long_agent_text = f"Agent Turn {i}: " + ("response " * 30)
        manager.add_turn(entity_id, long_user_text, long_agent_text)

        summary = manager.get_scratchpad_summary(entity_id)
        assert summary["active_turns"] <= 4
        assert summary["estimated_tokens"] <= 500
