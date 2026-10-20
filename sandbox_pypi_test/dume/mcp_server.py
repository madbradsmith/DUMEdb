import uuid
import os
import time
import logging
from pathlib import Path
from typing import Dict, Any, List, Union, Optional
from mcp.server.mcpserver import MCPServer

from dume.core.record import UnitRecord, uuid_to_hex, hex_to_uuid_bytes
from dume.schema.dictionary import SchemaDictionary, OpcodeSpec
from dume.storage.lmdb_engine import DUMEMemoryEngine
from dume.session.context_manager import BoundedBufferManager

logger = logging.getLogger("dume.mcp_server")

# Base Paths & In-Process Instances
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "lmdb_store"

memory_engine = DUMEMemoryEngine(db_path=DATA_DIR)
schema_dict = SchemaDictionary()
context_manager = BoundedBufferManager()

_DUME_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def normalize_entity_id(raw_id: str) -> bytes:
    """Normalizes raw string entity name or UUID hex to 16-byte binary UUID."""
    if isinstance(raw_id, bytes) and len(raw_id) == 16:
        return raw_id
    clean = str(raw_id).strip()
    try:
        return hex_to_uuid_bytes(clean)
    except Exception:
        return uuid.uuid5(_DUME_NS, clean).bytes


# Initialize MCPServer (mcp 2.x — FastMCP was renamed to MCPServer)
mcp = MCPServer("DUMEdb")


@mcp.tool()
def dume_read_state(entity_id: str = "DemoUser-01") -> Dict[str, Any]:
    """
    Direct zero-copy LMDB read of active state registers for a given entity_id.
    Decodes 32-byte records via SchemaDictionary into a human-readable dictionary.
    """
    canonical_uuid = normalize_entity_id(entity_id)
    records = memory_engine.get_all_active_registers(canonical_uuid)

    state_dict: Dict[str, Any] = {}
    for rec in records:
        spec = schema_dict.get_spec(rec.opcode)
        name = spec.name if spec else f"OPCODE_{rec.opcode}"
        formatted_val = schema_dict.format_value(rec.opcode, rec)
        state_dict[name] = formatted_val

    return state_dict


@mcp.tool()
def dume_commit_state(
    entity_id: str = "DemoUser-01",
    opcode_name: str = "",
    value: Union[str, int, float, bool] = ""
) -> str:
    """
    Atomically commits a discrete state register mutation to DUMEdb LMDB storage.
    Resolves opcode_name from SchemaDictionary (or auto-registers novel schema)
    and packs value into a hardware-aligned 32-byte record.
    """
    if not opcode_name:
        return "Error: opcode_name cannot be empty"

    clean_name = opcode_name.strip().upper()
    canonical_uuid = normalize_entity_id(entity_id)
    hex_id = uuid_to_hex(canonical_uuid)

    opcode = schema_dict.get_opcode_by_name(clean_name)
    spec: Optional[OpcodeSpec] = None

    if opcode is not None:
        spec = schema_dict.get_spec(opcode)
    else:
        # Novel schema discovery
        opcode = schema_dict.get_next_available_opcode()
        dt = "INT"
        if isinstance(value, bool):
            dt = "BOOL"
        elif isinstance(value, float):
            dt = "FLOAT"
        elif isinstance(value, str):
            dt = "ENUM"

        spec = OpcodeSpec(
            opcode=opcode,
            name=clean_name,
            description=f"Auto-registered via MCP tool for {clean_name}",
            data_type=dt,
            is_auto=True
        )
        schema_dict.register_opcode(spec, persist=True, is_custom=True)

    # Encode value into UnitRecord according to data type
    dt = spec.data_type if spec else "INT"
    rec: UnitRecord

    if dt == "FLOAT" or isinstance(value, float):
        try:
            f_val = float(value)
        except Exception:
            f_val = 0.0
        rec = UnitRecord.create_float(
            entity_id=canonical_uuid,
            opcode=opcode,
            float_val=f_val
        )
    elif dt == "BOOL" or isinstance(value, bool):
        b_val = 1 if bool(value) else 0
        rec = UnitRecord.create(
            entity_id=canonical_uuid,
            opcode=opcode,
            value=b_val
        )
    elif dt == "ENUM":
        enum_map = spec.enum_values if spec else {}
        matched_code: Optional[int] = None
        
        # Check string match in enum values
        val_str = str(value).strip().upper()
        for k, v in enum_map.items():
            if str(v).strip().upper() == val_str:
                matched_code = k
                break

        if matched_code is None:
            try:
                matched_code = int(value)
            except Exception:
                matched_code = 1
                if spec:
                    spec.enum_values[matched_code] = str(value)
                    schema_dict.save_to_disk()

        rec = UnitRecord.create(
            entity_id=canonical_uuid,
            opcode=opcode,
            value=matched_code
        )
    else:
        try:
            i_val = int(value)
        except Exception:
            i_val = 0
        rec = UnitRecord.create(
            entity_id=canonical_uuid,
            opcode=opcode,
            value=i_val
        )

    # Put record into LMDB
    memory_engine.put_record(rec)
    formatted_val = schema_dict.format_value(opcode, rec)

    return f"Successfully committed state [{clean_name} = {formatted_val}] for entity {hex_id[:8]} at timestamp {rec.timestamp}."


@mcp.tool()
def dume_list_schemas() -> List[Dict[str, Any]]:
    """
    Returns active DUMEdb schema dictionary specifications, including both pre-registered
    and auto-discovered [AUTO] opcodes.
    """
    specs = schema_dict.get_all_specs()
    return [spec.to_dict() for spec in specs]


@mcp.tool()
def dume_flush_scratchpad(entity_id: str = "DemoUser-01") -> str:
    """
    Resets the conversational scratchpad buffer for the specified entity_id
    while keeping persistent DUMEdb LMDB registers intact.
    """
    canonical_uuid = normalize_entity_id(entity_id)
    hex_id = uuid_to_hex(canonical_uuid)

    res = context_manager.flush_session_scratchpad(hex_id)

    return (
        f"Flushed {res.get('flushed_turns', 0)} conversational turns from scratchpad "
        f"for entity {hex_id[:8]}. Persistent LMDB registers remain intact."
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
