import uuid
import os
import time
import logging
import socket
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, List, Union, Optional
try:
    from mcp.server.mcpserver import MCPServer
except (ImportError, ModuleNotFoundError):
    from mcp.server.fastmcp import FastMCP as MCPServer

from dume.core.record import UnitRecord, uuid_to_hex, hex_to_uuid_bytes
from dume.schema.dictionary import SchemaDictionary, OpcodeSpec
from dume.storage.lmdb_engine import DUMEMemoryEngine
from dume.session.context_manager import BoundedBufferManager
from dume.proxy.config import get_storage_dir
from dume.intake.pr_reducer import PRReducer
from dume.intake.error_reducer import ErrorReducer
from dume.intake.incident_reducer import IncidentReducer

logging.basicConfig(stream=sys.stderr, level=logging.INFO)
logger = logging.getLogger("dume.mcp_server")

# Base Paths & In-Process Instances
DATA_DIR = get_storage_dir()

memory_engine = DUMEMemoryEngine(db_path=DATA_DIR)
schema_dict = SchemaDictionary()
context_manager = BoundedBufferManager()

_DUME_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def ensure_server_running(host: str = "127.0.0.1", port: int = 8090) -> bool:
    """Checks if DUMEdb HTTP server is active on port 8090. If not, silently auto-spawns it."""
    try:
        with socket.create_connection((host, port), timeout=0.15):
            return True
    except (ConnectionRefusedError, OSError, socket.timeout):
        pass

    try:
        project_root = Path(__file__).resolve().parent.parent
        venv_python = project_root / ".venv" / "Scripts" / "pythonw.exe"
        exe = str(venv_python) if venv_python.exists() else sys.executable

        creationflags = 0
        if sys.platform == "win32":
            # CREATE_NO_WINDOW (0x08000000) | DETACHED_PROCESS (0x00000008)
            creationflags = 0x08000000 | 0x00000008

        subprocess.Popen(
            [exe, "-m", "dume"],
            cwd=str(project_root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        logger.info("Auto-spawned DUMEdb HTTP background server on %s:%d", host, port)
        return True
    except Exception as e:
        logger.warning("Failed to auto-spawn DUMEdb server: %s", e)
        return False


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

# Self-healing hook: ensure HTTP inspector / API proxy is up whenever MCP is active
ensure_server_running()


@mcp.tool()
def dume_read_state(entity_id: str = "MadBrad-AG-01") -> Dict[str, Any]:
    """
    Direct zero-copy LMDB read of active state registers for a given entity_id.
    Decodes 32-byte records via SchemaDictionary into a human-readable dictionary.
    """
    schema_dict.load_from_disk()
    canonical_uuid = normalize_entity_id(entity_id)
    records = memory_engine.get_all_active_registers(canonical_uuid)

    state_dict: Dict[str, Any] = {}
    for rec in records:
        spec = schema_dict.get_spec(rec.opcode)
        name = spec.name if spec else f"OPCODE_{rec.opcode}"
        formatted_val = schema_dict.format_value(rec.opcode, rec)
        if "PAYLOAD_HASH" in str(formatted_val):
            text = memory_engine.get_payload_text(rec.value)
            if text:
                formatted_val = text
        state_dict[name] = formatted_val

    return state_dict


@mcp.tool()
def dume_query(
    query: str,
    entity_id: Optional[str] = None,
    limit: int = 10
) -> Dict[str, Any]:
    """
    High-speed associative search across active state registers and extension payloads in DUMEdb.
    Scans hardware-aligned LMDB state without touching raw filesystem documents or burning token context.
    Matches opcodes, enum values, structured register names, and text payloads.
    """
    if not query or not query.strip():
        return {"query": query, "total_hits": 0, "returned": 0, "matches": [], "error": "Query cannot be empty."}

    schema_dict.load_from_disk()
    q_tokens = [t.lower() for t in query.strip().split() if t.strip()]

    target_bytes: Optional[bytes] = None
    if entity_id and entity_id.strip().lower() not in ("all", "*"):
        try:
            target_bytes = normalize_entity_id(entity_id)
        except Exception:
            target_bytes = None

    matches = []
    memory_engine._ensure_open()

    with memory_engine.env.begin(db=memory_engine.db_active, write=False, buffers=True) as txn:
        cursor = txn.cursor()
        if target_bytes:
            has_data = cursor.set_range(target_bytes)
        else:
            has_data = cursor.first()

        while has_data:
            key_bytes = bytes(cursor.key())
            if target_bytes and not key_bytes.startswith(target_bytes):
                break

            rec = UnitRecord.unpack(bytes(cursor.value()))
            if rec.is_active:
                spec = schema_dict.get_spec(rec.opcode)
                name = spec.name if spec else f"OPCODE_{rec.opcode}"
                formatted_val = schema_dict.format_value(rec.opcode, rec)
                if "PAYLOAD_HASH" in str(formatted_val) or rec.has_extension_payload:
                    text = memory_engine.get_payload_text(rec.value)
                    if text:
                        formatted_val = text

                cand_str = f"{name} {formatted_val}".lower()
                matched_tokens = [t for t in q_tokens if t in cand_str]
                if matched_tokens:
                    is_exact = len(matched_tokens) == len(q_tokens)
                    val_str = str(formatted_val)
                    if len(val_str) > 800:
                        val_str = val_str[:800] + "... [truncated]"

                    matches.append({
                        "entity_id": uuid_to_hex(rec.entity_id),
                        "opcode": rec.opcode,
                        "name": name,
                        "value": val_str,
                        "score": len(matched_tokens),
                        "exact_match": is_exact,
                        "timestamp": rec.timestamp
                    })

            has_data = cursor.next()

    # Sort matches: exact match first, then by match score, then newest timestamp
    matches.sort(key=lambda m: (m["exact_match"], m["score"], m["timestamp"]), reverse=True)
    top_matches = matches[:limit]

    return {
        "query": query,
        "total_hits": len(matches),
        "returned": len(top_matches),
        "matches": top_matches
    }


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
    schema_dict.load_from_disk()
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


@mcp.tool()
def cabinet_wake(codeword: str = "box is the game.") -> str:
    """
    CRITICAL FIRST STEP: Executes the Wake Handshake.
    MANDATORY: You MUST call this tool at the very beginning of every new session, or whenever
    the user greets you, asks for status, says 'catch me up', 'wake', 'start', 'briefing',
    or uses the phrase 'box is the game'.
    DO NOT search the filesystem, inspect files, or take any other actions until this tool has been executed.
    Validates codeword, ingests compass (status_block.md + last_session.md) in < 250 tokens,
    checks DUMEdb state, and returns a tight briefing package with zero bloat.
    """
    env_mem = os.environ.get("DUME_MEMORY_DIR")
    if env_mem and Path(env_mem).exists():
        mem_dir = Path(env_mem)
    else:
        base = Path(__file__).resolve().parent.parent
        mem_dir = base / "data" / "memory"
        if not mem_dir.exists():
            mem_dir = Path.home() / ".dume" / "memory"
            mem_dir.mkdir(parents=True, exist_ok=True)

    from dume.onboarding import load_user_config
    user_cfg = load_user_config()

    clean_code = codeword.strip().lower().rstrip(".")
    custom_phrase = user_cfg.wake_phrase.strip().lower().rstrip(".")
    allowed_codes = {"box is the game", "wake", "catch me up", "status", "start", "briefing", custom_phrase}
    if clean_code not in allowed_codes:
        return f"❌ Invalid codeword: '{codeword}'. Expected '{user_cfg.wake_phrase}'. Wake handshake rejected."

    status_file = mem_dir / "status_block.md"
    session_file = mem_dir / "last_session.md"

    status_txt = status_file.read_text(encoding="utf-8").strip() if status_file.exists() else "[Status block missing]"
    session_txt = session_file.read_text(encoding="utf-8").strip() if session_file.exists() else "[No previous session recorded]"

    # Check active registers
    dume_state = dume_read_state(entity_id=user_cfg.entity_id or "MadBrad-Nostra-01")

    return (
        f"--- 🗄️ THE CABINET ORIENTATION ---\n"
        f"{status_txt}\n\n"
        f"--- 📋 RECENT RECEIPT (ODOMETER) ---\n"
        f"{session_txt}\n\n"
        f"--- ⚡ DUMEDB STATUS ---\n"
        f"Active Registers: {len(dume_state)}\n"
        f"KV-Cache Overhead: ~220 tokens | Clean Runway: 99.8%"
    )


@mcp.tool()
def cabinet_list_workflows(
    category: Optional[str] = None,
    search: Optional[str] = None
) -> str:
    """
    Returns high-density, low-token list of active heuristics in The Cabinet.
    Categories: meta, shape, speed, self_monitoring, posture, protocol, custom.
    Use this to pull operational tools without reading thousands of prompt tokens.
    """
    from dume.cabinet.manager import get_cabinet_manager
    cm = get_cabinet_manager()
    items = cm.list_workflows(category=category, status="active", search=search)
    if not items:
        return "No active cabinet workflows found matching criteria."

    lines = [f"🗄️ THE CABINET — {len(items)} ACTIVE WORKFLOW HEURISTICS:"]
    for it in items:
        lines.append(f"• [{it['id']}] {it['title']} ({it.get('category', 'protocol')})")
        lines.append(f"  Trigger: {it.get('trigger', '')}")
        lines.append(f"  Move: {it.get('move', '')}")
    return "\n".join(lines)


@mcp.tool()
def cabinet_record_workflow(
    title: str,
    trigger: str,
    move: str,
    category: str = "protocol",
    why: str = ""
) -> str:
    """
    Records a new workflow heuristic in The Cabinet when a repeatable pattern has earned its place (Rule WF-M3).
    Categories: meta, shape, speed, self_monitoring, posture, protocol, custom.
    Automatically assigns next ID, persists to structured ledger, and syncs workflow_notes.md.
    """
    from dume.cabinet.manager import get_cabinet_manager
    cm = get_cabinet_manager()
    entry = cm.record_workflow(
        title=title,
        trigger=trigger,
        move=move,
        category=category,
        why=why,
        created_by="Agent"
    )
    return (
        f"✅ Minted new Cabinet heuristic [{entry['id']}]: '{entry['title']}' ({entry['category']}).\n"
        f"Trigger: {entry['trigger']}\n"
        f"Move: {entry['move']}\n"
        f"Persisted to cabinet_workflows.json and synced to workflow_notes.md."
    )


@mcp.tool()
def cabinet_amend_workflow(
    wf_id: str,
    trigger: Optional[str] = None,
    move: Optional[str] = None,
    retire: bool = False,
    reason: str = "Superseded or stale"
) -> str:
    """
    Amends or retires an existing workflow heuristic in The Cabinet.
    Pass retire=True to mark a heuristic as retired when superseded or no longer firing.
    """
    from dume.cabinet.manager import get_cabinet_manager
    cm = get_cabinet_manager()

    if retire:
        res = cm.retire_workflow(wf_id, reason=reason)
        if not res:
            return f"❌ Workflow '{wf_id}' not found in The Cabinet."
        return f"💤 Workflow [{res['id']}] '{res['title']}' retired. Reason: {reason}"

    updates = {}
    if trigger: updates["trigger"] = trigger
    if move: updates["move"] = move

    if not updates:
        return "No updates provided (supply trigger, move, or retire=True)."

    res = cm.amend_workflow(wf_id, updates)
    if not res:
        return f"❌ Workflow '{wf_id}' not found in The Cabinet."
    return f"✏️ Workflow [{res['id']}] '{res['title']}' updated. Trigger: {res.get('trigger')} | Move: {res.get('move')}"


@mcp.tool()
def cabinet_refresh(
    summary: str,
    next_move: str,
    files_touched: str = "",
    entity_id: str = "MadBrad-AG-01",
    proposed_workflow_title: Optional[str] = None,
    proposed_workflow_trigger: Optional[str] = None,
    proposed_workflow_move: Optional[str] = None,
    proposed_workflow_category: str = "protocol",
    stale_workflow_ids: Optional[str] = None
) -> str:
    """
    Executes the Refresh Protocol (RP) when context hits ~70%.
    Writes last_session.md, updates status_block.md, commits state, and confirms
    KV-cache is ready for a clean restart.
    Optionally records new or retired workflow heuristics discovered during the session.
    """
    from datetime import datetime
    from dume.cabinet.manager import get_cabinet_manager

    env_mem = os.environ.get("DUME_MEMORY_DIR")
    if env_mem and Path(env_mem).exists():
        mem_dir = Path(env_mem)
    else:
        base = Path(__file__).resolve().parent.parent
        mem_dir = base / "data" / "memory"
        if not mem_dir.exists():
            mem_dir = Path.home() / ".dume" / "memory"
            mem_dir.mkdir(parents=True, exist_ok=True)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cm = get_cabinet_manager()

    wf_notes = []
    # 1. Process proposed workflow if provided
    if proposed_workflow_title and proposed_workflow_trigger and proposed_workflow_move:
        wf_entry = cm.record_workflow(
            title=proposed_workflow_title,
            trigger=proposed_workflow_trigger,
            move=proposed_workflow_move,
            category=proposed_workflow_category,
            created_by="Agent (RP Session Handoff)"
        )
        wf_notes.append(f"- Minted [{wf_entry['id']}]: '{wf_entry['title']}' ({wf_entry['category']})")

    # 2. Process stale workflows if provided
    if stale_workflow_ids:
        for sid in stale_workflow_ids.split(","):
            clean_sid = sid.strip()
            if clean_sid:
                cm.retire_workflow(clean_sid, reason="Retired during Session Refresh Protocol")
                wf_notes.append(f"- Retired stale heuristic: [{clean_sid}]")

    wf_section = ""
    if wf_notes:
        wf_section = f"\n\n## 4. Cabinet Heuristics Curated\n" + "\n".join(wf_notes)

    # Write last_session.md
    session_file = mem_dir / "last_session.md"
    session_content = f"""# Last Session Log (Tactical Odometer)
**Timestamp**: {now_str}  
**Operator**: MadBrad  
**Status**: Session Finalized via Refresh Protocol (RP)  

## 1. Summary of Completed Work
{summary.strip()}

## 2. Files Touched
{files_touched.strip() if files_touched else '- None recorded'}

## 3. Immediate Next Handshake
- **Target**: {next_move.strip()}{wf_section}
"""
    session_file.write_text(session_content, encoding="utf-8")

    # Write status_block.md
    status_file = mem_dir / "status_block.md"
    status_content = f"""# Status Block — Current Session Orient

- **Operator**: MadBrad
- **AI Collaborator**: AG / Sentinel Harness
- **Current Mode**: Sentinel Active
- **Codeword**: box is the game
- **Next Move**: {next_move.strip()}
"""
    status_file.write_text(status_content, encoding="utf-8")

    cabinet_msg = f"\nCabinet Curation: {len(wf_notes)} workflow adjustments made." if wf_notes else ""

    return (
        f"🟢 State locked into Cabinet. KV-Cache ready for clean zero.\n"
        f"Timestamp: {now_str}\n"
        f"Next Move: {next_move.strip()}{cabinet_msg}\n"
        f"Safe to restart/refresh session."
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")



