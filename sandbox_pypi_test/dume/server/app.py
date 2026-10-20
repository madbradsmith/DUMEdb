import os
import sys
import json
import uuid
import time
import struct
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional, List, Union
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Response
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

from dume.core.seed import seed_starter_profile

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if os.environ.get("DUME_TESTING") or os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
    DATA_DIR = BASE_DIR / "data" / "test_lmdb_store"
elif getattr(sys, "frozen", False) or os.environ.get("DUME_PUBLIC_DIST"):
    if sys.platform == "win32":
        local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        DATA_DIR = local_app_data / "DUMEdb" / "data" / "lmdb_store"
    else:
        DATA_DIR = Path.home() / ".dume" / "data" / "lmdb_store"
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
    # Seed neutral starter profile and pre-register preset schema packs on cold boot
    try:
        seed_starter_profile(memory_engine, schema_dict, scribe_committer)
    except Exception as e:
        print(f"[DUME Seed Warning] Starter seed initialization skipped: {e}", flush=True)

    # Startup: Start Background Scribe Worker (disabled during unit tests)
    if not os.environ.get("DUME_TESTING") and not os.environ.get("PYTEST_CURRENT_TEST") and "pytest" not in sys.modules:
        scribe_worker.start()

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
from dume.proxy.routes import proxy_router
from dume.proxy.config import get_proxy_config, set_proxy_config

app.include_router(proxy_router)

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


@app.get("/api/entities")
def get_entities():
    """Returns list of active entity identifiers stored in DUMEdb."""
    stored = memory_engine.get_all_entity_ids()
    friendly_entities = ["DemoUser-01"]
    
    madbrad_uuid_clean = normalize_entity_id("DemoUser-01").replace("-", "").lower()

    for item in stored:
        clean_item = item.replace("-", "").lower()
        if clean_item == madbrad_uuid_clean:
            continue
        friendly_entities.append(item)

    unique_entities = list(dict.fromkeys(friendly_entities))
    return {
        "count": len(unique_entities),
        "entities": unique_entities
    }


@app.post("/api/entities/purge")
def purge_unwanted_entities(keep_entity: str = "DemoUser-01"):
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
def purge_dirty_registers(entity_id: str = "DemoUser-01"):
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

        # Build custom synthesizer closure if provider or api_key requested
        def llm_fn(prompt: str) -> str:
            return ollama_synth.generate(
                prompt,
                provider=req.provider,
                api_key=req.api_key
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

        provider_name = ollama_synth.get_active_provider_name(provider=req.provider, custom_key=req.api_key)

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
            "synthetic_response": f"[DUME Error] {str(exc)}",
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
    decoded_list = [schema_dict.decode_record(r) for r in records]
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
    decoded_list = [schema_dict.decode_record(r) for r in records]
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
            "decoded": schema_dict.decode_record(r)
        })
    return {
        "entity_id": entity_id,
        "canonical_uuid": canonical_uuid,
        "count": len(items),
        "memory_pages": items
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
    from dume.__main__ import main as _cli_main
    _cli_main()
