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
from dume.proxy.config import get_storage_dir
from dume.intake.pr_reducer import PRReducer
from dume.intake.error_reducer import ErrorReducer
from dume.intake.incident_reducer import IncidentReducer

logger = logging.getLogger("dume.mcp_server")

# Base Paths & In-Process Instances
DATA_DIR = get_storage_dir()

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
def dume_read_state(entity_id: str = "MadBrad-Nostra-01") -> Dict[str, Any]:
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
    entity_id: str = "MadBrad-Nostra-01",
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
        rec = UnitRecord.create(
            entity_id=canonical_uuid,
            opcode=opcode,
            value=f_val
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
def dume_flush_scratchpad(entity_id: str = "MadBrad-Nostra-01") -> str:
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


@mcp.tool()
def dume_read_adr(adr_id: str) -> str:
    """
    Returns the content of the target Architectural Decision Record (ADR) markdown file
    from ~/.dume/assets/adrs/.
    """
    clean_id = str(adr_id).strip()
    assets_dir = Path.home() / ".dume" / "assets" / "adrs"
    if not assets_dir.exists():
        return f"Error: Asset directory '{assets_dir}' does not exist."

    matches = list(assets_dir.glob(f"*{clean_id}*.md"))
    if not matches:
        return f"ADR record '{clean_id}' not found in {assets_dir}."

    try:
        with open(matches[0], "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading ADR file '{matches[0].name}': {e}"


@mcp.tool()
def dume_get_error_details(fingerprint: str) -> str:
    """
    Returns the sanitized stack trace and diagnostic context for an active error fingerprint card
    from ~/.dume/assets/errors/.
    """
    clean_fp = str(fingerprint).strip()
    if not clean_fp.startswith("ERR_") and not clean_fp.startswith("err_"):
        clean_fp = f"ERR_{clean_fp.upper()}"
    else:
        clean_fp = clean_fp.upper()

    assets_dir = Path.home() / ".dume" / "assets" / "errors"
    if not assets_dir.exists():
        return f"Error: Asset directory '{assets_dir}' does not exist."

    matches = list(assets_dir.glob(f"*{clean_fp}*.md"))
    if not matches:
        return f"Error fingerprint record '{clean_fp}' not found in {assets_dir}."

    try:
        with open(matches[0], "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading error card file '{matches[0].name}': {e}"


@mcp.tool()
def dume_get_incident_rca(incident_id: str) -> str:
    """
    Returns the root cause analysis and resolution runbook for a logged incident card
    from ~/.dume/assets/incidents/.
    """
    clean_inc = str(incident_id).strip().upper()
    if not clean_inc.startswith("INC"):
        clean_inc = f"INC_{clean_inc}"

    assets_dir = Path.home() / ".dume" / "assets" / "incidents"
    if not assets_dir.exists():
        return f"Error: Asset directory '{assets_dir}' does not exist."

    matches = list(assets_dir.glob(f"*{clean_inc}*.md"))
    if not matches:
        return f"Incident record '{clean_inc}' not found in {assets_dir}."

    try:
        with open(matches[0], "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading incident file '{matches[0].name}': {e}"


@mcp.tool()
def dume_list_module_context(module: str = "") -> Dict[str, Any]:
    """
    Returns all known ADRs, active error fingerprints, and unresolved incidents
    linked to the specified module or system area.
    """
    clean_mod = str(module).strip().lower()
    base_assets = Path.home() / ".dume" / "assets"

    result = {
        "module": clean_mod or "all",
        "adrs": [],
        "errors": [],
        "incidents": []
    }

    # ADRs
    adrs_dir = base_assets / "adrs"
    if adrs_dir.exists():
        for p in adrs_dir.glob("*.md"):
            try:
                content = p.read_text(encoding="utf-8")
                if not clean_mod or clean_mod in p.name.lower() or clean_mod in content.lower():
                    title_line = content.splitlines()[0] if content.splitlines() else p.stem
                    result["adrs"].append({
                        "file": p.name,
                        "title": title_line.lstrip("#").strip(),
                        "path": str(p)
                    })
            except Exception:
                pass

    # Errors
    errors_dir = base_assets / "errors"
    if errors_dir.exists():
        for p in errors_dir.glob("*.md"):
            try:
                content = p.read_text(encoding="utf-8")
                if not clean_mod or clean_mod in p.name.lower() or clean_mod in content.lower():
                    title_line = content.splitlines()[0] if content.splitlines() else p.stem
                    result["errors"].append({
                        "file": p.name,
                        "fingerprint": p.stem,
                        "title": title_line.lstrip("#").strip(),
                        "path": str(p)
                    })
            except Exception:
                pass

    # Incidents
    incidents_dir = base_assets / "incidents"
    if incidents_dir.exists():
        for p in incidents_dir.glob("*.md"):
            try:
                content = p.read_text(encoding="utf-8")
                if not clean_mod or clean_mod in p.name.lower() or clean_mod in content.lower():
                    title_line = content.splitlines()[0] if content.splitlines() else p.stem
                    result["incidents"].append({
                        "file": p.name,
                        "incident_id": p.stem,
                        "title": title_line.lstrip("#").strip(),
                        "path": str(p)
                    })
            except Exception:
                pass

    return result


@mcp.tool()
def dume_ingest_enterprise(
    intake_type: str = "pr",
    payload: str = "",
    entity_id: str = "MadBrad-Nostra-01"
) -> str:
    """
    Ingests an enterprise JSON payload (PR design proposal, APM exception stack trace, or incident postmortem ticket).
    Scrubs secrets/PII, generates a Markdown card in ~/.dume/assets/, and commits active state pointers to DUMEdb.
    """
    if not payload:
        return "Error: payload cannot be empty."

    clean_type = intake_type.strip().lower()
    if clean_type in ("pr", "adr"):
        registers, asset_path = PRReducer.reduce_pr_payload(payload, entity_id=entity_id)
    elif clean_type in ("error", "apm"):
        registers, asset_path = ErrorReducer.reduce_error_payload(payload, entity_id=entity_id)
    elif clean_type in ("incident", "jira", "servicenow"):
        registers, asset_path = IncidentReducer.reduce_incident_payload(payload, entity_id=entity_id)
    else:
        return f"Error: Unknown intake_type '{intake_type}'. Must be 'pr', 'error', or 'incident'."

    committed = []
    for k, v in registers.items():
        res = dume_commit_state(entity_id=entity_id, opcode_name=k, value=v)
        committed.append(f"{k}={v}")

    return (
        f"Successfully ingested {clean_type} asset card at '{asset_path}'. "
        f"Committed {len(committed)} active state registers for {entity_id}: {', '.join(committed)}."
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")

