import os
import sys
import json
import uuid
import time
import struct
import asyncio
import re
import uvicorn
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional, List, Union
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Response, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from dume.core.record import generate_uuidv7_bytes, uuid_to_hex, hex_to_uuid_bytes, UnitRecord
from dume.schema.dictionary import SchemaDictionary, OpcodeSpec
from dume.storage.lmdb_engine import DUMEMemoryEngine
from dume.ingestion.parser import ConstrainedIngestionEngine, IngestionError
from dume.inference.grounded_engine import GroundedInferenceEngine
from dume.session.dispatcher import SessionDispatcher
from dume.scribe.committer import ScribeCommitter
from dume.scribe.worker import ScribeWorker
from dume.inference.local_llm import HybridSynthesizer, OllamaSynthesizer
from dume.intake.file_reducer import FileReducer
from dume.intake.pr_reducer import PRReducer
from dume.intake.error_reducer import ErrorReducer
from dume.intake.incident_reducer import IncidentReducer


# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if os.environ.get("DUME_TESTING") or os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
    DATA_DIR = BASE_DIR / "data" / "test_lmdb_store"
else:
    DATA_DIR = BASE_DIR / "data" / "lmdb_store"

# Core Instances
memory_engine = DUMEMemoryEngine(db_path=DATA_DIR)
schema_dict = SchemaDictionary()
ingestion_engine = ConstrainedIngestionEngine(schema_dict)
inference_engine = GroundedInferenceEngine(memory_engine, schema_dict)
ollama_synth = HybridSynthesizer()

session_dispatcher = SessionDispatcher(inference_engine)
scribe_committer = ScribeCommitter(memory_engine, schema_dict)
scribe_worker = ScribeWorker(session_dispatcher, scribe_committer, schema_dict)

# Active WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

ws_manager = ConnectionManager()

# Hook ScribeCommitter to WebSocket Broadcast
def on_scribe_mutation(event: Dict[str, Any]):
    # Schedule broadcast on active event loop
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(ws_manager.broadcast(event))
    except RuntimeError:
        pass

scribe_committer.register_listener(on_scribe_mutation)


# FastAPI Lifespan Handler
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start Background Scribe Worker (disabled during unit tests)
    if not os.environ.get("DUME_TESTING") and not os.environ.get("PYTEST_CURRENT_TEST") and "pytest" not in sys.modules:
        scribe_worker.start()

    # Pre-warm local model: load Nostra into RAM so first user request is fast
    if not os.environ.get("DUME_TESTING") and not os.environ.get("PYTEST_CURRENT_TEST"):
        async def _prewarm():
            try:
                import asyncio as _aio
                await _aio.sleep(2)  # Short delay to let server fully bind first
                if ollama_synth.is_available():
                    print("[DUME] Pre-warming Nostra model (loading into RAM)...", flush=True)
                    await _aio.to_thread(ollama_synth.generate, "hello", None)
                    print("[DUME] Nostra pre-warm complete. Model is hot and ready.", flush=True)
                else:
                    print("[DUME] Ollama not reachable at startup — skipping pre-warm.", flush=True)
            except Exception as e:
                print(f"[DUME] Pre-warm failed (non-fatal): {e}", flush=True)

        import asyncio as _aio
        _aio.get_event_loop().create_task(_prewarm())

    yield
    # Shutdown: Stop Worker
    await scribe_worker.stop()


app = FastAPI(
    title="DUME - Deterministic Unit-Record Memory Engine",
    version="0.2.0",
    description="Hardware-Aligned Zero-Copy Byte-Structured Memory Engine with Async Background Scribe",
    lifespan=lifespan
)

_DUME_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # UUID namespace for name-based IDs

def normalize_entity_id(raw: str) -> str:
    """
    Accepts any entity identifier string and returns a canonical UUID hex string.
    - 'NEW' / 'AUTO' / 'GENERATE' -> fresh UUIDv7
    - Valid UUID hex string        -> pass-through unchanged
    - Human-readable name          -> deterministic UUID5(name) so same name = same entity
    """
    if raw.upper() in ("NEW", "AUTO", "GENERATE"):
        return uuid_to_hex(generate_uuidv7_bytes())
    try:
        # Validate it's already a proper UUID hex string
        uuid.UUID(raw)
        return raw
    except ValueError:
        # Not a valid UUID — derive a stable UUID5 from the friendly name
        return str(uuid.uuid5(_DUME_NS, raw))

from dume.scribe.ingest import BatchIngestionEngine

batch_ingestion_engine = BatchIngestionEngine(
    memory_engine=memory_engine,
    schema_dict=schema_dict,
    scribe_committer=scribe_committer,
    context_manager=session_dispatcher.context_manager
)

# Attach DUME Engine dependencies to app.state for proxy routes
app.state.session_dispatcher = session_dispatcher
app.state.inference_engine = inference_engine
app.state.schema_dict = schema_dict
app.state.normalize_entity_id = normalize_entity_id
app.state.scribe_worker = scribe_worker
app.state.memory_engine = memory_engine
app.state.scribe_committer = scribe_committer
app.state.batch_ingestion_engine = batch_ingestion_engine

# Mount OpenAI Universal Proxy Router (/v1)
from dume.proxy.routes import proxy_router, ingest_directory_endpoint
from dume.proxy.config import get_proxy_config, set_proxy_config

app.include_router(proxy_router)
app.add_api_route("/dume/ingest/directory", ingest_directory_endpoint, methods=["POST"])


@app.get("/api/fs/list")
async def list_filesystem_directories(path: Optional[str] = None):
    """
    Fast, safe directory listing endpoint for the in-modal folder browser.
    Returns subdirectories, parent path, and quick-jump shortcuts (Desktop, Workspace, Home, Drives).
    Zero subprocesses, zero blocking, instant execution.
    """
    from pathlib import Path
    import os

    user_home = Path.home()
    workspace = BASE_DIR
    desktop_folders = user_home / "Desktop" / "folders"

    # Quick jump shortcuts
    quick_links = []
    if desktop_folders.is_dir():
        quick_links.append({"label": "📁 Desktop/folders", "path": str(desktop_folders.resolve())})
    if workspace.is_dir():
        quick_links.append({"label": "💻 DUMEdb-WORK", "path": str(workspace.resolve())})
    if (user_home / "Desktop").is_dir():
        quick_links.append({"label": "🖥️ Desktop", "path": str((user_home / "Desktop").resolve())})
    quick_links.append({"label": "🏠 Home", "path": str(user_home.resolve())})

    # Add Windows drive letters if on Windows
    if os.name == "nt":
        import string
        from ctypes import windll
        try:
            bitmask = windll.kernel32.GetLogicalDrives()
            for letter in string.ascii_uppercase:
                if bitmask & 1:
                    drive_path = f"{letter}:\\"
                    if os.path.exists(drive_path):
                        quick_links.append({"label": f"💾 {letter}:", "path": drive_path})
                bitmask >>= 1
        except Exception:
            pass

    # Resolve target directory
    if not path or not path.strip():
        if desktop_folders.is_dir():
            target = desktop_folders
        elif workspace.is_dir():
            target = workspace
        else:
            target = user_home
    else:
        try:
            target = Path(path.strip()).resolve()
            if not target.is_dir():
                if target.parent.is_dir():
                    target = target.parent
                else:
                    target = desktop_folders if desktop_folders.is_dir() else workspace
        except Exception:
            target = desktop_folders if desktop_folders.is_dir() else workspace

    dirs = []
    try:
        with os.scandir(str(target)) as entries:
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        name = entry.name
                        # Filter out system/hidden directories
                        if name.startswith(".") or name.startswith("$") or name.lower() in ("__pycache__", "node_modules", "system volume information", "recovery"):
                            continue
                        dirs.append({
                            "name": name,
                            "path": str(Path(entry.path).resolve())
                        })
                except (PermissionError, OSError):
                    continue
    except (PermissionError, OSError) as e:
        return {
            "status": "error",
            "error": f"Access denied: {e}",
            "current_path": str(target),
            "parent_path": str(target.parent) if target.parent != target else None,
            "directories": [],
            "quick_links": quick_links
        }

    dirs.sort(key=lambda d: d["name"].lower())
    parent_path = str(target.parent) if target.parent != target else None

    return {
        "status": "ok",
        "current_path": str(target),
        "parent_path": parent_path,
        "directories": dirs,
        "quick_links": quick_links
    }


@app.get("/api/utils/browse_directory")
@app.post("/api/utils/browse_directory")
async def browse_directory_endpoint(req: Optional[dict] = None):
    """Fallback endpoint redirecting callers to the fs/list API."""
    return await list_filesystem_directories()


@app.get("/api/utils/resolve_directory")
async def resolve_directory_endpoint(name: str):
    """
    Given a directory name (from client webkitdirectory picker),
    resolves the full local filesystem path across common user workspace paths.
    """
    from pathlib import Path
    import sys

    name_clean = name.strip().strip("/\\")
    if not name_clean:
        return {"found": False, "path": None}

    try:
        p = Path(name_clean)
        if p.is_dir():
            return {"found": True, "path": str(p.resolve())}
    except Exception:
        pass

    user_home = Path.home()
    candidates = [
        BASE_DIR.parent / name_clean,
        BASE_DIR / name_clean,
        user_home / "Desktop" / "folders" / name_clean,
        user_home / "Desktop" / name_clean,
        user_home / "Downloads" / name_clean,
        user_home / "Documents" / name_clean,
        user_home / name_clean,
    ]

    for cand in candidates:
        try:
            if cand.is_dir() and cand.name.lower() == name_clean.lower():
                return {"found": True, "path": str(cand.resolve())}
        except Exception:
            pass

    try:
        folders_dir = user_home / "Desktop" / "folders"
        if folders_dir.is_dir():
            for child in folders_dir.iterdir():
                if child.is_dir() and child.name.lower() == name_clean.lower():
                    return {"found": True, "path": str(child.resolve())}
    except Exception:
        pass

    return {"found": False, "path": None}


# Static UI Mount
UI_DIR = BASE_DIR / "dume" / "ui" / "inspector"
if UI_DIR.exists():
    app.mount("/inspector", StaticFiles(directory=str(UI_DIR), html=True), name="inspector")

class MutationRequest(BaseModel):
    entity_id: str
    opcode: Any
    value: Any
    timestamp: Optional[int] = None


class TombstoneRequest(BaseModel):
    entity_id: str
    opcode: int


class InferenceRequest(BaseModel):
    entity_id: str
    user_prompt: str


def get_presets_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        p = Path(sys._MEIPASS) / "dume" / "schemas" / "presets"
        if p.exists():
            return p
    return Path(__file__).resolve().parent.parent / "schemas" / "presets"


class SchemaRegisterRequest(BaseModel):
    opcode: Optional[int] = None
    name: str
    data_type: str = "INT"
    description: str = ""
    enum_values: Optional[Dict[int, str]] = None
    unit: Optional[str] = None


class PackLoadRequest(BaseModel):
    pack_name: str


class CustomSchemaRequest(BaseModel):
    name: str
    data_type: str = "INT"
    description: Optional[str] = ""
    unit: Optional[str] = None
    enum_values: Optional[Dict[Union[int, str], str]] = None


class PromoteSchemaRequest(BaseModel):
    opcode: int


class TurnRequest(BaseModel):
    entity_id: str
    user_text: str
    agent_text: Optional[str] = ""
    provider: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    endpoint_url: Optional[str] = None


# Endpoints
@app.get("/")
def read_root():
    return {
        "engine": "DUME (Deterministic Unit-Record Memory Engine)",
        "version": "0.2.0",
        "background_scribe": "Active",
        "inspector_ui": "/inspector/index.html",
        "docs": "/docs"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "storage": memory_engine.get_stats(),
        "scribe_queue_size": session_dispatcher.queue.qsize()
    }


from dume.onboarding import DumeUserConfig, load_user_config, save_user_config, scaffold_ide_rules


class OnboardingSetupRequest(BaseModel):
    operator_name: str
    agent_name: str
    wake_phrase: str
    port: Optional[int] = 8095
    connected_ides: Optional[List[str]] = Field(default_factory=lambda: ["antigravity", "cursor", "windsurf", "copilot"])


@app.get("/api/v1/onboarding/status")
def get_onboarding_status():
    cfg = load_user_config()
    return {
        "onboarding_completed": cfg.onboarding_completed,
        "config": cfg.to_dict()
    }


@app.post("/api/v1/onboarding/setup")
def setup_onboarding(req: OnboardingSetupRequest):
    entity_id = f"{req.operator_name.strip()}-{req.agent_name.strip()}-01"
    clean_wake = req.wake_phrase.strip()
    ides = req.connected_ides or ["antigravity", "cursor", "windsurf", "copilot"]
    chosen_port = req.port if req.port and req.port > 0 else 8095

    cfg = DumeUserConfig(
        onboarding_completed=True,
        operator_name=req.operator_name.strip(),
        agent_name=req.agent_name.strip(),
        entity_id=entity_id,
        wake_phrase=clean_wake,
        port=chosen_port,
        connected_ides=ides
    )
    save_user_config(cfg)
    files_created = scaffold_ide_rules(cfg, target_dir=BASE_DIR)

    return {
        "success": True,
        "onboarding_completed": True,
        "config": cfg.to_dict(),
        "files_scaffolded": files_created
    }


@app.post("/api/v1/onboarding/reset")
def reset_data_endpoint():
    """Resets onboarding configuration and purges memory state to test first-time load."""
    from dume.onboarding import reset_user_config
    reset_user_config()
    memory_engine.purge_all_data()
    return {
        "success": True,
        "message": "All data cleared. Reset to pristine first-time load state."
    }


class WorkflowCreateRequest(BaseModel):
    title: str
    trigger: str
    move: str
    category: str = "protocol"
    why: Optional[str] = ""
    source: Optional[str] = ""
    created_by: Optional[str] = "Operator"
    custom_id: Optional[str] = None


class WorkflowPatchRequest(BaseModel):
    title: Optional[str] = None
    trigger: Optional[str] = None
    move: Optional[str] = None
    category: Optional[str] = None
    why: Optional[str] = None
    source: Optional[str] = None
    status: Optional[str] = None


class WorkflowRetireRequest(BaseModel):
    reason: Optional[str] = "Superseded or stale"


@app.get("/api/cabinet/workflows")
def get_cabinet_workflows(
    category: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None
):
    """Lists heuristics from The Cabinet with optional category, status, or search filters."""
    from dume.cabinet.manager import get_cabinet_manager
    cm = get_cabinet_manager()
    items = cm.list_workflows(category=category, status=status, search=search)
    return {"count": len(items), "workflows": items}


@app.post("/api/cabinet/workflows")
def create_cabinet_workflow(req: WorkflowCreateRequest):
    """Mints a new workflow heuristic in The Cabinet."""
    from dume.cabinet.manager import get_cabinet_manager
    cm = get_cabinet_manager()
    item = cm.record_workflow(
        title=req.title,
        trigger=req.trigger,
        move=req.move,
        category=req.category,
        why=req.why or "",
        source=req.source or "",
        created_by=req.created_by or "Operator",
        custom_id=req.custom_id
    )
    return {"success": True, "workflow": item}


@app.patch("/api/cabinet/workflows/{wf_id}")
def update_cabinet_workflow(wf_id: str, req: WorkflowPatchRequest):
    """Amends an existing workflow heuristic."""
    from dume.cabinet.manager import get_cabinet_manager
    cm = get_cabinet_manager()
    updates = {k: v for k, v in req.dict().items() if v is not None}
    item = cm.amend_workflow(wf_id, updates)
    if not item:
        raise HTTPException(status_code=404, detail=f"Workflow '{wf_id}' not found")
    return {"success": True, "workflow": item}


@app.post("/api/cabinet/workflows/{wf_id}/retire")
def retire_cabinet_workflow(wf_id: str, req: Optional[WorkflowRetireRequest] = None):
    """Retires a workflow heuristic to prevent stale bloat."""
    from dume.cabinet.manager import get_cabinet_manager
    cm = get_cabinet_manager()
    reason = req.reason if req else "Superseded or stale"
    item = cm.retire_workflow(wf_id, reason=reason)
    if not item:
        raise HTTPException(status_code=404, detail=f"Workflow '{wf_id}' not found")
    return {"success": True, "workflow": item}


@app.post("/api/cabinet/workflows/{wf_id}/reactivate")
def reactivate_cabinet_workflow(wf_id: str):
    """Reactivates a retired workflow heuristic."""
    from dume.cabinet.manager import get_cabinet_manager
    cm = get_cabinet_manager()
    item = cm.reactivate_workflow(wf_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Workflow '{wf_id}' not found")
    return {"success": True, "workflow": item}


@app.post("/api/cabinet/workflows/{wf_id}/fire")
def record_cabinet_workflow_fire(wf_id: str):
    """Increments the recorded fire count of a workflow."""
    from dume.cabinet.manager import get_cabinet_manager
    cm = get_cabinet_manager()
    item = cm.record_fire(wf_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Workflow '{wf_id}' not found")
    return {"success": True, "workflow": item}


@app.get("/api/cabinet/health")
def get_cabinet_health():
    """Groundskeeper health check for The Cabinet."""
    from dume.cabinet.manager import get_cabinet_manager
    cm = get_cabinet_manager()
    return cm.get_groundskeeper_health()


@app.post("/api/cabinet/sync")
def sync_cabinet():
    """Forces 2-way sync from structured ledger to workflow_notes.md."""
    from dume.cabinet.manager import get_cabinet_manager
    cm = get_cabinet_manager()
    cm.sync_to_markdown()
    return {"success": True, "message": "The Cabinet synchronized to markdown."}



@app.post("/api/inspector/tombstone")
def tombstone_register_endpoint(req: TombstoneRequest):
    """Soft-deletes (tombstones) an active state register for the given entity."""
    canonical_uuid = normalize_entity_id(req.entity_id)
    canonical_uuid_bytes = hex_to_uuid_bytes(canonical_uuid)

    success = memory_engine.tombstone_register(canonical_uuid_bytes, req.opcode)
    if success:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(ws_manager.broadcast({
                "type": "MUTATION_COMMIT",
                "timestamp": int(time.time()),
                "entity_id": canonical_uuid,
                "opcode": req.opcode,
                "opcode_name": schema_dict.get_opcode_name(req.opcode),
                "human_value": "<TOMBSTONE>",
                "raw_hex": "",
                "decoded": {"is_tombstone": True}
            }))
        except RuntimeError:
            pass
    return {"success": success, "entity_id": req.entity_id, "opcode": req.opcode}


class EntityPatchRequest(BaseModel):
    alias: Optional[str] = None
    is_archived: Optional[bool] = None


ENTITY_METADATA: Dict[str, Dict[str, Any]] = {}


@app.get("/api/entities")
def get_entities():
    """Returns list of active entity identifiers stored in DUMEdb along with metadata."""
    stored = memory_engine.get_all_entity_ids()
    cfg = load_user_config()
    default_id = cfg.entity_id if (cfg and cfg.entity_id) else "MadBrad-Nostra-01"

    friendly_entities = []
    if cfg.onboarding_completed and cfg.entity_id:
        friendly_entities.append(cfg.entity_id)
    elif default_id:
        friendly_entities.append(default_id)

    default_uuid_clean = normalize_entity_id(default_id).replace("-", "").lower()

    for item in stored:
        clean_item = item.replace("-", "").lower()
        if clean_item == default_uuid_clean:
            continue
        friendly_entities.append(item)

    unique_entities = list(dict.fromkeys(friendly_entities))
    return {
        "count": len(unique_entities),
        "entities": unique_entities,
        "metadata": ENTITY_METADATA
    }


@app.patch("/api/entities/{entity_id}")
async def patch_entity_endpoint(entity_id: str, req: EntityPatchRequest):
    """
    Updates entity metadata such as human alias or archived status.
    """
    canonical_uuid = normalize_entity_id(entity_id)
    meta = ENTITY_METADATA.setdefault(canonical_uuid, {})
    if req.alias is not None:
        meta["alias"] = req.alias.strip()
    if req.is_archived is not None:
        meta["is_archived"] = req.is_archived

    await ws_manager.broadcast({
        "event": "ENTITY_METADATA_MUTATION",
        "entity_id": entity_id,
        "canonical_uuid": canonical_uuid,
        "metadata": meta,
        "timestamp": int(time.time() * 1000)
    })
    return {
        "success": True,
        "entity_id": entity_id,
        "canonical_uuid": canonical_uuid,
        "metadata": meta
    }


@app.delete("/api/entities/{entity_id}")
async def delete_entity_endpoint(entity_id: str):
    """
    Hard purges target entity from LMDB active registers, history logs, and session scratchpad.
    """
    canonical_uuid = normalize_entity_id(entity_id)
    res = memory_engine.delete_entity(canonical_uuid)
    session_dispatcher.flush_scratchpad(canonical_uuid)
    if entity_id in ENTITY_METADATA:
        ENTITY_METADATA.pop(entity_id, None)
    if canonical_uuid in ENTITY_METADATA:
        ENTITY_METADATA.pop(canonical_uuid, None)

    await ws_manager.broadcast({
        "event": "ENTITY_PURGE",
        "entity_id": entity_id,
        "canonical_uuid": canonical_uuid,
        "timestamp": int(time.time() * 1000)
    })
    return {
        "success": True,
        "entity_id": entity_id,
        "canonical_uuid": canonical_uuid,
        "active_deleted": res["active_deleted"],
        "history_deleted": res["history_deleted"]
    }


@app.post("/api/entities/purge")
def purge_unwanted_entities(keep_entity: str = "MadBrad-Nostra-01"):
    """Deletes all active and historical records for all entities except keep_entity."""
    target_uuid_str = normalize_entity_id(keep_entity)
    target_bytes = hex_to_uuid_bytes(target_uuid_str)
    
    active_deleted = 0
    history_deleted = 0

    with memory_engine.env.begin(write=True) as txn:
        # Purge active_state
        cursor = txn.cursor(db=memory_engine.db_active)
        for key, val in list(cursor):
            if not bytes(key).startswith(target_bytes):
                txn.delete(key, db=memory_engine.db_active)
                active_deleted += 1

        # Purge history_log
        cursor = txn.cursor(db=memory_engine.db_history)
        for key, val in list(cursor):
            if not bytes(key).startswith(target_bytes):
                txn.delete(key, db=memory_engine.db_history)
                history_deleted += 1

@app.post("/api/entities/purge_dirty_registers")
def purge_dirty_registers(entity_id: str = "MadBrad-Nostra-01"):
    """Deletes dirty opcodes (2020, 2025, 2026, 2027, 2030) from db_active for entity_id."""
    canonical_uuid = normalize_entity_id(entity_id)
    canonical_uuid_bytes = hex_to_uuid_bytes(canonical_uuid)
    dirty_opcodes = {2020, 2025, 2026, 2027, 2030}
    deleted_count = 0

    with memory_engine.env.begin(write=True) as txn:
        cursor = txn.cursor(db=memory_engine.db_active)
        for key, val in list(cursor):
            key_bytes = bytes(key)
            if key_bytes.startswith(canonical_uuid_bytes) and len(key_bytes) >= 18:
                op = struct.unpack("!H", key_bytes[16:18])[0]
                if op in dirty_opcodes:
                    txn.delete(key, db=memory_engine.db_active)
                    deleted_count += 1

    return {"success": True, "entity_id": entity_id, "deleted_count": deleted_count}


@app.get("/api/proxy/config")
def get_proxy_configuration():
    """Returns active Universal OpenAI Proxy configuration status."""
    return get_proxy_config().to_dict()


@app.post("/api/proxy/config")
def update_proxy_configuration(req: Dict[str, Any]):
    """Updates proxy configuration dynamically at runtime."""
    cfg = set_proxy_config(
        upstream_base_url=req.get("upstream_base_url"),
        upstream_api_key=req.get("upstream_api_key"),
        default_entity_id=req.get("default_entity_id")
    )
    return cfg.to_dict()


@app.get("/api/schema")
def get_schema():
    # Reload custom opcodes from disk on every request so that schemas
    # auto-registered by the MCP server (a separate process) are always
    # visible without restarting the inspector server.
    schema_dict.load_from_disk()
    return {
        "version": schema_dict.version,
        "next_available_opcode": schema_dict.get_next_available_opcode(),
        "next_available_custom_opcode": schema_dict.get_next_available_custom_opcode(),
        "opcodes": [
            {
                "opcode": spec.opcode,
                "name": spec.name,
                "description": spec.description,
                "data_type": spec.data_type,
                "enum_values": spec.enum_values,
                "unit": spec.unit,
                "is_auto": spec.is_auto
            }
            for spec in schema_dict.get_all_specs()
        ]
    }


@app.get("/api/schema/packs")
def get_preset_schema_packs():
    """Lists available preset domain packs and their loading status."""
    presets_dir = get_presets_dir()
    packs = []
    schema_dict.load_from_disk()
    all_opcodes = {spec.opcode for spec in schema_dict.get_all_specs()}

    if presets_dir.exists():
        for file in sorted(presets_dir.glob("*.json")):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                pack_name = data.get("name", file.stem)
                pack_opcodes = data.get("opcodes", [])
                opcode_ids = [op["opcode"] for op in pack_opcodes if "opcode" in op]
                is_loaded = len(opcode_ids) > 0 and all(op_id in all_opcodes for op_id in opcode_ids)

                packs.append({
                    "name": pack_name,
                    "title": data.get("title", pack_name.replace("_", " ").title()),
                    "description": data.get("description", ""),
                    "opcode_count": len(pack_opcodes),
                    "opcodes": pack_opcodes,
                    "is_loaded": is_loaded
                })
            except Exception as e:
                pass

    return {"packs": packs}


@app.post("/api/schema/packs/load")
async def load_preset_schema_pack(req: PackLoadRequest):
    """Merges definitions from a preset domain pack into registered_schemas.json."""
    presets_dir = get_presets_dir()
    pack_file = presets_dir / f"{req.pack_name}.json"
    if not pack_file.exists():
        raise HTTPException(status_code=404, detail=f"Preset pack '{req.pack_name}' not found")

    try:
        with open(pack_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        loaded_specs = []
        for item in data.get("opcodes", []):
            spec = OpcodeSpec.from_dict(item)
            try:
                registered = schema_dict.register_opcode(spec, persist=True, is_custom=True)
                loaded_specs.append(registered.to_dict())
            except ValueError:
                # Idempotent skip if opcode ID / Name is already registered
                if spec.opcode in schema_dict._opcodes:
                    loaded_specs.append(schema_dict.get_spec(spec.opcode).to_dict())

        await ws_manager.broadcast({
            "event": "SCHEMA_MUTATION",
            "pack_name": req.pack_name,
            "timestamp": int(time.time() * 1000)
        })

        return {
            "success": True,
            "pack_name": req.pack_name,
            "loaded_count": len(loaded_specs),
            "opcodes": loaded_specs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load preset pack: {e}")


@app.post("/api/schema/custom")
async def create_custom_opcode(req: CustomSchemaRequest):
    """Mints a novel custom opcode in the 3xxx ID range."""
    try:
        clean_name = req.name.strip().upper()
        existing_id = schema_dict.get_opcode_by_name(clean_name)
        if existing_id:
            existing_spec = schema_dict.get_spec(existing_id)
            return {
                "success": True,
                "spec": existing_spec.to_dict(),
                "next_available_custom_opcode": schema_dict.get_next_available_custom_opcode()
            }

        opcode_id = schema_dict.get_next_available_custom_opcode()
        enum_map = req.enum_values or {}
        clean_enum_map = {int(k): str(v) for k, v in enum_map.items()}

        spec = OpcodeSpec(
            opcode=opcode_id,
            name=clean_name,
            description=req.description or f"Custom opcode for {clean_name}",
            data_type=req.data_type.upper(),
            enum_values=clean_enum_map,
            unit=req.unit,
            is_auto=False
        )

        registered_spec = schema_dict.register_opcode(spec, persist=True, is_custom=True)

        await ws_manager.broadcast({
            "event": "SCHEMA_MUTATION",
            "spec": registered_spec.to_dict(),
            "timestamp": int(time.time() * 1000)
        })

        return {
            "success": True,
            "spec": registered_spec.to_dict(),
            "next_available_custom_opcode": schema_dict.get_next_available_custom_opcode()
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to mint custom opcode: {exc}")


class IntakeRegisterPair(BaseModel):
    key: str
    value: Union[str, int, float, bool]


class IntakeCommitRequest(BaseModel):
    registers: List[IntakeRegisterPair]
    flush_scratchpad: Optional[bool] = False


@app.post("/api/entities/{entity_id}/intake/upload")
async def upload_and_reduce_file(
    entity_id: str,
    file: UploadFile = File(...),
    prefix: Optional[str] = Form("")
):
    """
    Multimodal File Intake Endpoint:
    1. Saves uploaded file to ~/.dume/assets/<sha256>.<ext> without storing binary blob in LMDB.
    2. Runs FileReducer (.xlsx, .csv, images, media) to extract candidate KEY=VALUE registers.
    """
    file_bytes = await file.read()
    canonical_uuid = normalize_entity_id(entity_id)
    entity_cfg = ENTITY_METADATA.get(canonical_uuid) or ENTITY_METADATA.get(entity_id)

    reduction = FileReducer.reduce_file(
        file_bytes=file_bytes,
        filename=file.filename or "uploaded_file.bin",
        prefix=prefix or "",
        synthesizer=ollama_synth,
        entity_config=entity_cfg
    )

    return {
        "success": True,
        "entity_id": entity_id,
        "canonical_uuid": canonical_uuid,
        "filename": reduction["filename"],
        "asset_hash": reduction["asset_hash"],
        "asset_path": reduction["asset_path"],
        "candidates": reduction["registers"]
    }


@app.post("/api/entities/{entity_id}/intake/commit")
async def commit_intake_registers(entity_id: str, req: IntakeCommitRequest):
    """
    Commits approved candidate registers atomically into LMDB db_active and logs to db_history.
    """
    canonical_uuid = normalize_entity_id(entity_id)
    schema_dict.load_from_disk()
    committed_events = []
    new_opcodes_registered = False

    try:
        for reg in req.registers:
            raw_key = reg.key.strip()
            raw_val = str(reg.value).strip()

            if not raw_key:
                continue

            spec = schema_dict.get_spec_by_name(raw_key)
            if not spec:
                next_op = schema_dict.get_next_available_custom_opcode()
                spec = OpcodeSpec(
                    opcode=next_op,
                    name=raw_key.upper().replace(" ", "_"),
                    description=f"Auto-registered intake key {raw_key}",
                    data_type="STRING_REF",
                    enum_values={},
                    is_auto=False
                )
                schema_dict.register_opcode(spec, persist=False, is_custom=True)
                new_opcodes_registered = True

            event = scribe_committer.commit_mutation(
                entity_id=canonical_uuid,
                opcode_identifier=spec.opcode,
                raw_value=raw_val,
                timestamp=int(time.time())
            )
            if event:
                committed_events.append(event)

        if new_opcodes_registered:
            schema_dict.save_to_disk()

        if req.flush_scratchpad:
            session_dispatcher.flush_scratchpad(canonical_uuid)

        await ws_manager.broadcast({
            "event": "INTAKE_COMMIT",
            "entity_id": entity_id,
            "canonical_uuid": canonical_uuid,
            "committed_count": len(committed_events),
            "timestamp": int(time.time() * 1000)
        })

        return {
            "success": True,
            "entity_id": entity_id,
            "canonical_uuid": canonical_uuid,
            "committed_count": len(committed_events),
            "events": committed_events
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to commit intake registers: {str(e)}")


@app.post("/api/schema/promote")
async def promote_auto_opcode_route(req: PromoteSchemaRequest):
    """Re-classifies an auto-discovered [AUTO] opcode (2xxx) into the permanent registry."""
    try:
        promoted_spec = schema_dict.promote_auto_opcode(req.opcode)

        await ws_manager.broadcast({
            "event": "SCHEMA_MUTATION",
            "spec": promoted_spec.to_dict(),
            "timestamp": int(time.time() * 1000)
        })

        return {
            "success": True,
            "spec": promoted_spec.to_dict()
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to promote opcode: {exc}")


@app.get("/api/schema/export")
def export_schema_dictionary():
    """Downloads active schema dictionary as an exportable JSON attachment."""
    schema_dict.load_from_disk()
    export_data = {
        "version": schema_dict.version,
        "exported_at": int(time.time()),
        "opcodes": [spec.to_dict() for spec in schema_dict.get_all_specs()]
    }
    json_bytes = json.dumps(export_data, indent=2).encode("utf-8")
    return Response(
        content=json_bytes,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=dume_schema_export.json"}
    )


@app.post("/api/schema/register")
async def register_schema_opcode(req: SchemaRegisterRequest):
    """
    Registers a new dynamic opcode spec in the SchemaDictionary at runtime.
    Persists to disk and broadcasts a SCHEMA_MUTATION event to all active Web UI clients.
    """
    try:
        opcode_id = req.opcode
        if opcode_id is None or opcode_id == 0:
            opcode_id = schema_dict.get_next_available_opcode()

        enum_map = req.enum_values or {}
        clean_enum_map = {int(k): str(v) for k, v in enum_map.items()}

        spec = OpcodeSpec(
            opcode=opcode_id,
            name=req.name.strip().upper(),
            description=req.description,
            data_type=req.data_type.upper(),
            enum_values=clean_enum_map,
            unit=req.unit
        )

        registered_spec = schema_dict.register_opcode(spec, persist=True)

        # Broadcast SCHEMA_MUTATION over WebSocket
        await ws_manager.broadcast({
            "event": "SCHEMA_MUTATION",
            "spec": registered_spec.to_dict(),
            "timestamp": int(time.time() * 1000)
        })

        return {
            "success": True,
            "spec": registered_spec.to_dict(),
            "next_available_opcode": schema_dict.get_next_available_opcode()
        }
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to register schema opcode: {exc}")


@app.post("/api/session/turn")
async def handle_conversation_turn(req: TurnRequest):
    """
    Foreground Fast Path Turn Dispatcher.
    1. Returns prompt register context instantly to chat agent with zero disk/lock latency.
    2. Enqueues turn payload onto Background Scribe queue for out-of-band extraction & persistence.
    Always returns valid JSON — never an HTML error page.
    """
    try:
        raw_entity_id = req.entity_id
        canonical_uuid = normalize_entity_id(raw_entity_id)

        # Dispatch turn (zero-latency fast path)
        dispatch_res = session_dispatcher.dispatch_turn(
            entity_id=canonical_uuid,
            user_text=req.user_text,
            agent_text=req.agent_text or ""
        )

        # Build custom synthesizer closure if provider, model_name, endpoint_url, or api_key requested
        def llm_fn(prompt: str) -> str:
            return ollama_synth.generate(
                prompt,
                provider=req.provider,
                api_key=req.api_key,
                model_name=req.model_name,
                endpoint_url=req.endpoint_url
            )

        # Perform grounded synthesis response asynchronously with bounded scratchpad context
        t_start = time.perf_counter()
        synth_res = await asyncio.to_thread(
            inference_engine.generate,
            canonical_uuid,
            req.user_text,
            llm_fn,
            dispatch_res["bounded_history"]
        )
        t_end = time.perf_counter()

        synth_ms = (t_end - t_start) * 1000
        output_text = synth_res.get("response", "")
        token_count = max(1, len(output_text.split()))  # Rough token count estimate by words
        tokens_per_sec = (token_count / (synth_ms / 1000.0)) if synth_ms > 0 else 0.0

        # Update last turn in scratchpad with final agent output
        session_dispatcher.update_agent_response(canonical_uuid, output_text)
        scratchpad_summary = session_dispatcher.context_manager.get_scratchpad_summary(canonical_uuid)

        provider_name = ollama_synth.get_active_provider_name(
            provider=req.provider,
            custom_key=req.api_key,
            model_name=req.model_name
        )

        return {
            "entity_id": raw_entity_id,
            "canonical_uuid": canonical_uuid,
            "dispatch_latency_ms": dispatch_res["dispatch_latency_ms"],
            "synthesis_ms": synth_ms,
            "tokens_per_sec": round(tokens_per_sec, 1),
            "output_tokens": token_count,
            "register_context": dispatch_res["register_context"],
            "synthetic_response": output_text,
            "scribe_queue_size": dispatch_res["queue_size"],
            "ollama_active": ollama_synth.is_available(),
            "provider_name": provider_name,
            "scratchpad": scratchpad_summary
        }

    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        # Always return JSON so the browser never sees an HTML error page
        return {
            "entity_id": req.entity_id,
            "error": str(exc),
            "traceback": tb,
            "synthetic_response": f"[Nostra Error] {str(exc)}",
            "ollama_active": False
        }


@app.post("/api/session/flush/{entity_id}")
def flush_scratchpad(entity_id: str):
    """
    Explicitly flushes in-memory conversational scratchpad for entity.
    Preserves all DUMEdb active registers and history audit logs intact.
    """
    canonical_uuid = normalize_entity_id(entity_id)
    res = session_dispatcher.flush_scratchpad(canonical_uuid)
    res["entity_id"] = entity_id
    res["canonical_uuid"] = canonical_uuid
    return res


@app.get("/api/session/scratchpad/{entity_id}")
def get_scratchpad_status(entity_id: str):
    """Returns current scratchpad buffer metrics for target entity."""
    canonical_uuid = normalize_entity_id(entity_id)
    summary = session_dispatcher.context_manager.get_scratchpad_summary(canonical_uuid)
    summary["entity_id"] = entity_id
    summary["canonical_uuid"] = canonical_uuid
    return summary


@app.post("/api/mutate")
def mutate_state(req: MutationRequest):
    entity_id_str = normalize_entity_id(req.entity_id)

    event = scribe_committer.commit_mutation(
        entity_id=entity_id_str,
        opcode_identifier=req.opcode,
        raw_value=req.value,
        timestamp=req.timestamp
    )

    if not event:
        raise HTTPException(status_code=400, detail="Invalid mutation candidate or schema violation")

    return {"success": True, "event": event}


@app.get("/api/registers/{entity_id}")
def get_active_registers(entity_id: str):
    schema_dict.load_from_disk()
    canonical_uuid = normalize_entity_id(entity_id)
    records = memory_engine.get_all_active_registers(canonical_uuid)
    decoded_list = [schema_dict.decode_record(r, resolver=memory_engine.get_payload_text) for r in records]
    return {
        "entity_id": entity_id,
        "canonical_uuid": canonical_uuid,
        "count": len(decoded_list),
        "registers": decoded_list
    }


@app.get("/api/history/{entity_id}")
def get_entity_history(entity_id: str, limit: int = 50):
    schema_dict.load_from_disk()
    canonical_uuid = normalize_entity_id(entity_id)
    records = memory_engine.get_history(canonical_uuid, limit=limit)
    decoded_list = [schema_dict.decode_record(r, resolver=memory_engine.get_payload_text) for r in records]
    return {
        "entity_id": entity_id,
        "canonical_uuid": canonical_uuid,
        "count": len(decoded_list),
        "history": decoded_list
    }


@app.get("/api/inspector/hex/{entity_id}")
def get_inspector_hex(entity_id: str):
    schema_dict.load_from_disk()
    canonical_uuid = normalize_entity_id(entity_id)
    records = memory_engine.get_all_active_registers(canonical_uuid)
    items = []
    for r in records:
        packed = r.pack()
        items.append({
            "opcode": r.opcode,
            "raw_hex": packed.hex(),
            "uuid_hex": packed[:16].hex(),
            "opcode_hex": packed[16:18].hex(),
            "value_hex": packed[18:26].hex(),
            "timestamp_hex": packed[26:30].hex(),
            "flags_hex": packed[30:32].hex(),
            "decoded": schema_dict.decode_record(r, resolver=memory_engine.get_payload_text)
        })
    return {
        "entity_id": entity_id,
        "canonical_uuid": canonical_uuid,
        "count": len(items),
        "memory_pages": items
    }


class EnterpriseIntakeRequest(BaseModel):
    entity_id: str = "MadBrad-Nostra-01"
    intake_type: str  # "pr", "error", or "incident"
    payload: Union[str, Dict[str, Any]]
    flush_scratchpad: bool = False


@app.post("/api/intake/enterprise")
def process_enterprise_intake(req: EnterpriseIntakeRequest):
    canonical_uuid = normalize_entity_id(req.entity_id)
    intake_type = req.intake_type.strip().lower()

    if intake_type in ("pr", "adr"):
        registers, asset_path = PRReducer.reduce_pr_payload(req.payload, entity_id=req.entity_id)
    elif intake_type in ("error", "apm"):
        registers, asset_path = ErrorReducer.reduce_error_payload(req.payload, entity_id=req.entity_id)
    elif intake_type in ("incident", "jira", "servicenow"):
        registers, asset_path = IncidentReducer.reduce_incident_payload(req.payload, entity_id=req.entity_id)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown enterprise intake_type: '{req.intake_type}'")

    committed_events = []
    schema_dict.load_from_disk()
    for k, v in registers.items():
        clean_key = k.strip().upper()
        if schema_dict.get_opcode_by_name(clean_key) is None:
            dt = "INT" if isinstance(v, int) else ("FLOAT" if isinstance(v, float) else "STRING_REF")
            spec = OpcodeSpec(
                opcode=schema_dict.get_next_available_custom_opcode(),
                name=clean_key,
                description=f"Enterprise intake opcode for {clean_key}",
                data_type=dt,
                is_custom=True
            )
            schema_dict.register_opcode(spec, persist=True, is_custom=True)

        evt = scribe_committer.commit_mutation(entity_id=canonical_uuid, opcode_identifier=clean_key, raw_value=v)
        if evt:
            committed_events.append(evt)

    if req.flush_scratchpad:
        session_dispatcher.flush_scratchpad(canonical_uuid)

    return {
        "status": "success",
        "intake_type": intake_type,
        "entity_id": req.entity_id,
        "committed_count": len(committed_events),
        "asset_path": asset_path,
        "registers": registers
    }


def _ensure_starter_knowledge_cards(base_assets: Path):
    """Seed starter architectural decisions, guide specs, and diagnostic cards if assets are empty."""
    adrs_dir = base_assets / "adrs"
    docs_dir = base_assets / "docs"
    errors_dir = base_assets / "errors"
    incidents_dir = base_assets / "incidents"

    for d in [adrs_dir, docs_dir, errors_dir, incidents_dir]:
        d.mkdir(parents=True, exist_ok=True)

    if not list(adrs_dir.glob("*.md")):
        adr1 = adrs_dir / "ADR-001-Zero-Token-LMDB-Memory-Engine.md"
        adr1.write_text(
            "# ADR-001: Zero-Token Deterministic LMDB Memory Engine\n\n"
            "## Status\nAccepted & Active (Core Architecture)\n\n"
            "## Context\n"
            "Large Language Model agent workflows suffer from exponential context window bloat, "
            "non-deterministic state drift, and runaway token burn when retaining conversational and system "
            "history in raw prompt strings.\n\n"
            "## Decision\n"
            "We implemented DUMEdb using a lightning-fast, zero-overhead memory-mapped key-value engine (LMDB). "
            "Unit-record registers are stored as 16-bit integer opcodes mapping to deterministic state values.\n\n"
            "## Consequences\n"
            "- **Token Burn**: Reduced by >95% compared to raw prompt stuffing.\n"
            "- **Latency**: Sub-millisecond direct memory-mapped read/write (< 0.2ms).\n"
            "- **Persistence**: ACID-compliant persistence across agent restarts and machine reboots.\n"
            "- **Living Cabinet**: Real-time sync with Sentinel and Nostra protocols.\n",
            encoding="utf-8"
        )

        adr2 = adrs_dir / "ADR-002-Nostra-Protocol-Living-Cabinet.md"
        adr2.write_text(
            "# ADR-002: Nostra Protocol & Living Cabinet Synchronization\n\n"
            "## Status\nAccepted & Active\n\n"
            "## Context\n"
            "AI agent handoffs require seamless context transfer between sessions, background daemons, and "
            "IDE copilots without burning thousands of tokens re-summarizing previous tasks.\n\n"
            "## Decision\n"
            "Adopted the **Nostra Handshake Protocol**:\n"
            "1. Zero-turn wake handshake (`cabinet_wake`) validates codeword and reads living compass in < 250 tokens.\n"
            "2. Real-time background scribe synchronizes register state and dirty cache pages.\n"
            "3. Session handoff (`cabinet_refresh`) writes the tactical odometer and next immediate actions.\n\n"
            "## Consequences\n"
            "- Instant resumption across session boundaries.\n"
            "- Zero filesystem rummaging or grep scans needed to orient fresh agent instances.\n"
            "- Predictable, low-entropy handoff receipts.\n",
            encoding="utf-8"
        )

    if not list(docs_dir.glob("*.md")):
        doc1 = docs_dir / "DOC-001-DUME-Studio-Operator-Guide.md"
        doc1.write_text(
            "# DOC-001: DUME Studio Operator Guide\n\n"
            "## Overview\n"
            "DUME Studio is the interactive control plane for the Deterministic Unit-Record Memory Engine (DUMEdb). "
            "It bridges human operators and autonomous AI agents through real-time state visualization, schema pack "
            "management, and instant knowledge ingestion.\n\n"
            "## Core Subsystems\n"
            "- **State Registers**: 16-bit opcode registers holding current project phase, agent state, error codes, and operational flags.\n"
            "- **Knowledge Base**: Deep diagnostic cards, ADRs, error patterns, and project specs available instantly on-demand without context bloating.\n"
            "- **Schema Studio**: Custom opcode minting and industry domain preset packs (e.g. Game Dev, Enterprise Workflow, Web Architecture).\n"
            "- **Living Cabinet**: Zero-token handoff odometer tracking agent progress and next moves.\n\n"
            "## Default Ports & Endpoints\n"
            "- Default Studio Port: `8095`\n"
            "- Universal OpenAI Proxy: `http://localhost:8095/v1`\n"
            "- Background Scribe Feed: `ws://localhost:8095/api/ws/inspector`\n",
            encoding="utf-8"
        )

    if not list(errors_dir.glob("*.md")):
        err1 = errors_dir / "ERR-001-LMDB-Lock-Collision-Resolution.md"
        err1.write_text(
            "# ERR-001: LMDB Lock Collision & Concurrent Multi-Process Write Contention\n\n"
            "## Pattern\n"
            "`MDB_LOCKS_FULL` or `Environment lock failed: permission denied`\n\n"
            "## Root Cause\n"
            "Occurs when multiple processes attempt to initialize read-write LMDB environments simultaneously on Windows "
            "without shared lock flags or without closing existing write transactions.\n\n"
            "## Resolution\n"
            "1. Set `max_dbs=10` and `sync=False` for high-throughput write stages.\n"
            "2. Wrap write transactions in explicit context managers `with env.begin(write=True) as txn:`.\n"
            "3. Ensure stale process locks are cleaned up on SIGTERM/atexit hooks.\n",
            encoding="utf-8"
        )

    if not list(incidents_dir.glob("*.md")):
        inc1 = incidents_dir / "INC-001-Context-Bloat-Float-Recovery.md"
        inc1.write_text(
            "# INC-001: Context Bloat Float & Runaway Token Pressure Recovery\n\n"
            "## Incident Summary\n"
            "Agent sessions exceeding ~70% context capacity experienced drift and degraded tool precision "
            "prior to automated compacting.\n\n"
            "## Root Cause\n"
            "Verbose conversational transcripts retaining duplicate file dumps in context instead of delegating "
            "to unit registers.\n\n"
            "## Corrective Action & Standard Procedure\n"
            "1. Implemented **Bloat Watch** Odometer on every message turn.\n"
            "2. Flushed scratchpad turns via `dume_flush_scratchpad` at turn threshold.\n"
            "3. Preserved core state in LMDB opcodes 1000-1099.\n",
            encoding="utf-8"
        )


@app.get("/api/assets/list")
def list_knowledge_assets():
    base_assets = Path.home() / ".dume" / "assets"
    _ensure_starter_knowledge_cards(base_assets)
    items = []
    seen_paths = set()

    # Search standard category subfolders
    for cat in ["adrs", "docs", "errors", "incidents"]:
        c_dir = base_assets / cat
        if c_dir.exists():
            for p in sorted(c_dir.glob("*.md"), key=os.path.getmtime, reverse=True):
                if str(p) in seen_paths:
                    continue
                seen_paths.add(str(p))
                try:
                    content = p.read_text(encoding="utf-8")
                    title = content.splitlines()[0].lstrip("#").strip() if content.splitlines() else p.stem
                    word_count = len(content.split())
                    est_tokens = int(word_count * 1.33)
                    items.append({
                        "category": cat.rstrip("s"),
                        "filename": p.name,
                        "title": title,
                        "path": str(p),
                        "mtime": os.path.getmtime(p),
                        "size_bytes": p.stat().st_size,
                        "word_count": word_count,
                        "est_tokens_saved": est_tokens
                    })
                except Exception:
                    pass

    # Search root assets folder for any hydrated notes or specs
    if base_assets.exists():
        for p in base_assets.glob("*.md"):
            if str(p) in seen_paths:
                continue
            seen_paths.add(str(p))
            try:
                content = p.read_text(encoding="utf-8")
                title = content.splitlines()[0].lstrip("#").strip() if content.splitlines() else p.stem
                word_count = len(content.split())
                items.append({
                    "category": "doc",
                    "filename": p.name,
                    "title": title,
                    "path": str(p),
                    "mtime": os.path.getmtime(p),
                    "size_bytes": p.stat().st_size,
                    "word_count": word_count,
                    "est_tokens_saved": int(word_count * 1.33)
                })
            except Exception:
                pass

    # Search repo data/assets if present
    repo_assets = BASE_DIR / "data" / "assets"
    if repo_assets.exists():
        for p in repo_assets.glob("**/*.md"):
            if str(p) in seen_paths:
                continue
            seen_paths.add(str(p))
            try:
                content = p.read_text(encoding="utf-8")
                title = content.splitlines()[0].lstrip("#").strip() if content.splitlines() else p.stem
                word_count = len(content.split())
                items.append({
                    "category": "doc",
                    "filename": p.name,
                    "title": title,
                    "path": str(p),
                    "mtime": os.path.getmtime(p),
                    "size_bytes": p.stat().st_size,
                    "word_count": word_count,
                    "est_tokens_saved": int(word_count * 1.33)
                })
            except Exception:
                pass

    items.sort(key=lambda x: x.get("mtime", 0), reverse=True)
    return {"count": len(items), "assets": items}


@app.get("/api/assets/read")
def read_knowledge_asset(category: str, filename: str):
    base_assets = Path.home() / ".dume" / "assets"
    repo_assets = BASE_DIR / "data" / "assets"

    candidates = [
        base_assets / category / filename,
        base_assets / (category + "s") / filename,
        base_assets / (category.rstrip("s")) / filename,
        base_assets / filename,
        repo_assets / category / filename,
        repo_assets / (category + "s") / filename,
        repo_assets / filename
    ]

    target_path = None
    for c in candidates:
        if c.exists() and c.is_file():
            target_path = c
            break

    if not target_path:
        raise HTTPException(status_code=404, detail="Asset card not found.")

    try:
        content = target_path.read_text(encoding="utf-8")
        word_count = len(content.split())
        est_tokens = int(word_count * 1.33)
        return {
            "filename": target_path.name,
            "category": category,
            "content": content,
            "path": str(target_path),
            "mtime": os.path.getmtime(target_path),
            "size_bytes": target_path.stat().st_size,
            "word_count": word_count,
            "est_tokens_saved": est_tokens
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CreateKnowledgeAssetRequest(BaseModel):
    category: str = "adr"
    title: str
    content: str
    filename: Optional[str] = None


@app.post("/api/assets/create")
def create_knowledge_asset(req: CreateKnowledgeAssetRequest):
    base_assets = Path.home() / ".dume" / "assets"
    cat_dir_name = req.category.strip().lower()
    if not cat_dir_name.endswith("s"):
        cat_dir_name += "s"
    target_dir = base_assets / cat_dir_name
    target_dir.mkdir(parents=True, exist_ok=True)

    if req.filename and req.filename.strip():
        safe_fname = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", req.filename.strip())
        if not safe_fname.endswith(".md"):
            safe_fname += ".md"
    else:
        slug = re.sub(r"[^a-zA-Z0-9_\-]", "-", req.title.strip().lower())
        slug = re.sub(r"-+", "-", slug).strip("-")
        prefix = req.category.upper().rstrip("S")
        safe_fname = f"{prefix}-{slug}.md" if slug else f"{prefix}-{int(time.time())}.md"

    target_path = target_dir / safe_fname
    target_path.write_text(req.content, encoding="utf-8")

    word_count = len(req.content.split())
    return {
        "success": True,
        "filename": safe_fname,
        "category": req.category.lower().rstrip("s"),
        "title": req.title,
        "path": str(target_path),
        "word_count": word_count,
        "est_tokens_saved": int(word_count * 1.33)
    }


@app.websocket("/api/ws/inspector")
async def websocket_inspector_feed(websocket: WebSocket):
    """Real-Time WebSocket endpoint broadcasting live Background Scribe commits."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Receive heartbeat pings from browser client
            data = await websocket.receive_text()
    except (WebSocketDisconnect, Exception):
        ws_manager.disconnect(websocket)


def main():
    """CLI Entrypoint for running DUMEdb server."""
    from dume.__main__ import main as run_main
    run_main()



