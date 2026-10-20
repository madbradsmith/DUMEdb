import pytest
from dume.mcp_server import (
    dume_read_state,
    dume_commit_state,
    dume_list_schemas,
    dume_flush_scratchpad,
    context_manager,
    normalize_entity_id,
    mcp
)
from dume.core.record import uuid_to_hex


def test_mcp_tool_discovery():
    """
    Acceptance Criteria 1: test_mcp_tool_discovery
    Assert all 4 tools (dume_read_state, dume_commit_state, dume_list_schemas, dume_flush_scratchpad)
    are exported by MCPServer with valid schemas.
    """
    tools = mcp._tool_manager.list_tools()
    tool_names = [t.name for t in tools]

    assert "dume_read_state" in tool_names
    assert "dume_commit_state" in tool_names
    assert "dume_list_schemas" in tool_names
    assert "dume_flush_scratchpad" in tool_names
    assert "dume_read_adr" in tool_names
    assert "dume_get_error_details" in tool_names
    assert "dume_get_incident_rca" in tool_names
    assert "dume_list_module_context" in tool_names
    assert "dume_ingest_enterprise" in tool_names


def test_mcp_read_and_commit_cycle():
    """
    Acceptance Criteria 2: test_mcp_read_and_commit_cycle
    1. Call dume_commit_state with UI_THEME = DARK for test entity.
    2. Call dume_read_state and assert DARK is returned instantly.
    """
    entity_id = "MadBrad-MCP-Cycle-Test-01"

    # Commit state mutation
    commit_res = dume_commit_state(
        entity_id=entity_id,
        opcode_name="UI_THEME",
        value="DARK"
    )
    assert "Successfully committed state" in commit_res
    assert "UI_THEME" in commit_res

    # Read state back
    state = dume_read_state(entity_id=entity_id)
    assert "UI_THEME" in state
    assert state["UI_THEME"] == "DARK"


def test_mcp_scratchpad_flush():
    """
    Acceptance Criteria 3: test_mcp_scratchpad_flush
    1. Set up simulated turns in context buffer.
    2. Call dume_flush_scratchpad.
    3. Assert active context turn count drops to 0 while LMDB registers persist.
    """
    entity_id = "MadBrad-MCP-Flush-Test-01"
    canonical_uuid = normalize_entity_id(entity_id)
    hex_id = uuid_to_hex(canonical_uuid)

    # 1. Commit persistent state register
    dume_commit_state(entity_id=entity_id, opcode_name="ACCOUNT_TIER", value="PRO")

    # 2. Populate simulated conversational scratchpad
    context_manager.add_turn(hex_id, user_text="Hello, DUME!", agent_text="Hello! How can I assist?")
    context_manager.add_turn(hex_id, user_text="Set my tier to PRO", agent_text="Account tier set to PRO.")

    turns_before = context_manager.get_bounded_history(hex_id)
    assert len(turns_before) == 2

    # 3. Execute scratchpad flush
    flush_res = dume_flush_scratchpad(entity_id=entity_id)
    assert "Flushed 2 conversational turns" in flush_res

    # 4. Assert scratchpad buffer cleared while LMDB persistent state persists
    turns_after = context_manager.get_bounded_history(hex_id)
    assert len(turns_after) == 0

    state_after = dume_read_state(entity_id=entity_id)
    assert state_after.get("ACCOUNT_TIER") == "PRO"
