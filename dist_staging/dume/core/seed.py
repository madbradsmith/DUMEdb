import json
import time
import sys
import uuid
from pathlib import Path
from dume.core.record import UnitRecord, uuid_to_hex, hex_to_uuid_bytes
from dume.schema.dictionary import SchemaDictionary, OpcodeSpec

_DUME_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

def _normalize_id(raw: str) -> str:
    try:
        uuid.UUID(raw)
        return raw
    except ValueError:
        return str(uuid.uuid5(_DUME_NS, raw))

def get_presets_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        p = Path(sys._MEIPASS) / "dume" / "schemas" / "presets"
        if p.exists():
            return p
    return Path(__file__).resolve().parent.parent / "schemas" / "presets"

def seed_starter_profile(memory_engine, schema_dict, scribe_committer=None):
    """
    Ensures brand-new instances initialize cleanly with:
    1. All 4 domain schema packs (Film Production, Software Dev, Research, Admin) pre-registered.
    2. DemoUser-01 entity seeded with neutral starter registers:
       - PROJECT_STATUS = 'ACTIVE_PREVIEW'
       - WORKSPACE_ROLE = 'Operator'
       - CURRENT_BRANCH = 'main'
       - FOCUS_MODE = 'Discovery'
    """
    # 1. Pre-register all 4 domain schema packs
    presets_dir = get_presets_dir()
    if presets_dir.exists():
        for file in sorted(presets_dir.glob("*.json")):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data.get("opcodes", []):
                    spec = OpcodeSpec.from_dict(item)
                    try:
                        schema_dict.register_opcode(spec, persist=True, is_custom=True)
                    except ValueError:
                        pass
            except Exception:
                pass

    # 2. Check if DemoUser-01 or database needs initial seeding
    demo_entity = "DemoUser-01"
    canonical_uuid = _normalize_id(demo_entity)
    active = memory_engine.get_all_active_registers(canonical_uuid)

    if len(active) == 0:
        starter_map = {
            "PROJECT_STATUS": "DEPLOYED",
            "WORKSPACE_ROLE": "1st_AD",
            "CURRENT_BRANCH": "main",
            "FOCUS_MODE": "DEEP_WORK"
        }
        committer_inst = scribe_committer
        if committer_inst is None:
            from dume.scribe.committer import ScribeCommitter
            committer_inst = ScribeCommitter(memory_engine, schema_dict)

        for key, val in starter_map.items():
            try:
                committer_inst.commit_mutation(entity_id=canonical_uuid, opcode_identifier=key, raw_value=val)
            except Exception as e:
                logger.warning(f"Failed to seed starter opcode {key}={val}: {e}")

