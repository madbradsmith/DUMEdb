import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class CabinetManager:
    """
    Manages The Cabinet: A living heuristics and workflow repository.
    Maintains a structured JSON ledger (cabinet_workflows.json) with bidirectional
    synchronization to the human-readable markdown manifest (workflow_notes.md).
    """

    GENERIC_STARTER_WORKFLOWS = [
        {
            "id": "WF-GEN-01",
            "title": "ZERO-TURN ORIENTATION / ORIENT BEFORE ACTING",
            "category": "protocol",
            "trigger": "Session start, wake command, or context handoff",
            "move": "Execute cabinet_wake to ingest status block and receipts in <250 tokens without rummaging filesystem",
            "why": "Eliminates token waste and amnesia; establishes ground truth immediately",
            "source": "DUME Core Protocols",
            "created_by": "System (Generic Template)",
            "status": "active",
            "created_at": "2026-10-19T00:00:00",
            "last_fired": None,
            "fire_count": 0
        },
        {
            "id": "WF-GEN-02",
            "title": "THE BLOAT METER WATCH (RP PROTOCOL)",
            "category": "self_monitoring",
            "trigger": "Bloat Meter reaches >= 75% (~90,000 tokens)",
            "move": "Warn operator and execute cabinet_refresh handoff before auto-compaction occurs",
            "why": "Preserves continuous session state and avoids uncontrolled model compaction",
            "source": "DUME Core Protocols",
            "created_by": "System (Generic Template)",
            "status": "active",
            "created_at": "2026-10-19T00:00:00",
            "last_fired": None,
            "fire_count": 0
        },
        {
            "id": "WF-GEN-03",
            "title": "FRANK'S LAW (RECEIPTS OVER DELETIONS)",
            "category": "protocol",
            "trigger": "State mutation, schema change, or obsolete record",
            "move": "Append timestamped state transitions; never silently overwrite or delete history",
            "why": "Deletions is where the lies live; immutable audit trails guarantee truth",
            "source": "Frank (DUME Field Philosophy)",
            "created_by": "System (Generic Template)",
            "status": "active",
            "created_at": "2026-10-19T00:00:00",
            "last_fired": None,
            "fire_count": 0
        },
        {
            "id": "WF-GEN-04",
            "title": "REGISTER-FIRST FAST PATH",
            "category": "speed",
            "trigger": "Agent needs project mode, state flag, or current operational setting",
            "move": "Query DUMEdb LMDB unit-records via opcode before initiating fuzzy search",
            "why": "Sub-microsecond retrieval at zero prompt token burn",
            "source": "IBM 1401 Unit-Record Paradigm",
            "created_by": "System (Generic Template)",
            "status": "active",
            "created_at": "2026-10-19T00:00:00",
            "last_fired": None,
            "fire_count": 0
        },
        {
            "id": "WF-GEN-05",
            "title": "OPERATOR GROUND TRUTH ALIGNMENT",
            "category": "posture",
            "trigger": "Telemetry or state contradicts operator observation",
            "move": "Immediately pause and calibrate to disk/hardware reality (no cosmetic theater)",
            "why": "Prioritizes real math and verified receipts over polite hallucination",
            "source": "DUME Core Philosophy",
            "created_by": "System (Generic Template)",
            "status": "active",
            "created_at": "2026-10-19T00:00:00",
            "last_fired": None,
            "fire_count": 0
        }
    ]

    def __init__(self, cabinet_dir: Optional[Path] = None):
        self.cabinet_dir = self._resolve_cabinet_dir(cabinet_dir)
        self.cabinet_dir.mkdir(parents=True, exist_ok=True)
        self.json_path = self.cabinet_dir / "cabinet_workflows.json"
        self.md_path = self.cabinet_dir / "workflow_notes.md"
        self._ensure_initialized()

    def _resolve_cabinet_dir(self, explicit: Optional[Path] = None) -> Path:
        if explicit and explicit.exists():
            return explicit
        
        # 1. Explicit environment variable
        env_dir = os.environ.get("DUME_CABINET_DIR")
        if env_dir and Path(env_dir).exists():
            return Path(env_dir)

        # 2. Project standalone directory
        base = Path(__file__).resolve().parent.parent.parent
        proj_dir = base / "data" / "cabinet"
        if proj_dir.exists():
            return proj_dir

        # 3. User home directory fallback
        return Path.home() / ".dume" / "cabinet"

    def _ensure_initialized(self):
        """Initializes JSON from markdown if missing, or seeds generic starter heuristics."""
        if not self.json_path.exists():
            if self.md_path.exists():
                parsed = self._parse_markdown(self.md_path.read_text(encoding="utf-8"))
                if parsed:
                    self._save_json(parsed)
                    return
            # Seed generic starter workflows
            self._save_json(self.GENERIC_STARTER_WORKFLOWS)
            if not self.md_path.exists():
                self._sync_to_markdown()

    def _load_json(self) -> List[Dict[str, Any]]:
        if not self.json_path.exists():
            return []
        try:
            return json.loads(self.json_path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save_json(self, items: List[Dict[str, Any]]):
        self.json_path.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")

    def _parse_markdown(self, text: str) -> List[Dict[str, Any]]:
        """Parses [WF-*] items from workflow_notes.md into structured dicts."""
        items = []
        now_str = datetime.now().isoformat()

        # Regex to capture [WF-XX] TITLE blocks
        pattern = re.compile(
            r"\[(WF-[A-Z0-9]+)\]\s+([^\n\r]+)(.*?)(?=(\[(WF-[A-Z0-9]+)\])|$)",
            re.DOTALL
        )

        cat_map = {
            "M": "meta",
            "S": "shape",
            "P": "speed",
            "X": "self_monitoring",
            "T": "posture",
            "R": "protocol"
        }

        for match in pattern.finditer(text):
            wf_id = match.group(1).strip()
            title = match.group(2).strip().strip("*").strip()
            body = match.group(3).strip()

            trigger = ""
            move = ""
            why = ""
            source = ""

            trig_m = re.search(r"Trigger:\s*(.*?)(?=(Move:|Why:|Failure mode|Source:|$))", body, re.DOTALL | re.IGNORECASE)
            if trig_m:
                trigger = " ".join(trig_m.group(1).split())

            move_m = re.search(r"Move:\s*(.*?)(?=(Why:|Failure mode|Trigger:|Source:|$))", body, re.DOTALL | re.IGNORECASE)
            if move_m:
                move = " ".join(move_m.group(1).split())

            why_m = re.search(r"(Why:|Failure mode it prevents:)\s*(.*?)(?=(Trigger:|Move:|Source:|$))", body, re.DOTALL | re.IGNORECASE)
            if why_m:
                why = " ".join(why_m.group(2).split())

            src_m = re.search(r"Source:\s*(.*?)(?=(Trigger:|Move:|Why:|$))", body, re.DOTALL | re.IGNORECASE)
            if src_m:
                source = " ".join(src_m.group(1).split())

            if not move and not trigger:
                # If unformatted block, treat body as move
                move = " ".join(body.split())

            prefix = wf_id.split("-")[1][0].upper() if "-" in wf_id and len(wf_id.split("-")[1]) > 0 else "R"
            category = cat_map.get(prefix, "protocol")

            items.append({
                "id": wf_id,
                "title": title,
                "category": category,
                "trigger": trigger or "Session context or pattern recognition",
                "move": move or title,
                "why": why,
                "source": source,
                "status": "active",
                "fire_count": 1,
                "last_fired_at": now_str,
                "created_by": "MadBrad",
                "created_at": now_str,
                "updated_at": now_str
            })

        return items

    def sync_to_markdown(self):
        """Regenerates workflow_notes.md from the structured JSON ledger."""
        items = self._load_json()
        now_str = datetime.now().strftime("%m%d%Y")

        lines = [
            "---",
            "# WORKFLOW-NOTES — THE LIVING CABINET",
            f"# Last Synced: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "# Managed by DUMEdb Cabinet Engine",
            "---",
            "",
            "```",
            "WORKFLOW-NOTES",
            now_str,
            "================================================",
            "FILE 3 OF 3 — THE CABINET (LIVING HEURISTICS)",
            "================================================",
            "",
            "PURPOSE",
            "This file is a functional tool manifest. It catalogs every",
            "heuristic, posture, rule, and protocol picked up across sessions",
            "that future-me can fire as an operational tool.",
            "",
            "The cabinet grows. Add tools when earned (WF-M3).",
            "Retire tools that don't fire.",
            "================================================",
            "```",
            ""
        ]

        # Group by category
        categories = ["meta", "shape", "speed", "self_monitoring", "posture", "protocol", "custom"]
        cat_labels = {
            "meta": "META-RULES (operate the cabinet itself)",
            "shape": "SHAPE TOOLS (how to describe what you see)",
            "speed": "SPEED TOOLS (how to move on a task)",
            "self_monitoring": "SELF-MONITORING TOOLS (catching cognitive loops)",
            "posture": "POSTURE TOOLS (how to be in the room)",
            "protocol": "OPERATIONAL PROTOCOLS",
            "custom": "USER & PROJECT HEURISTICS"
        }

        for cat in categories:
            cat_items = [it for it in items if it.get("category") == cat and it.get("status") == "active"]
            if not cat_items:
                continue

            lines.append("=" * 48)
            lines.append(cat_labels.get(cat, cat.upper()))
            lines.append("=" * 48)
            lines.append("")

            for it in cat_items:
                lines.append(f"[{it['id']}] {it['title']}")
                lines.append(f"  Trigger: {it.get('trigger', '')}")
                lines.append(f"  Move: {it.get('move', '')}")
                if it.get("why"):
                    lines.append(f"  Why: {it['why']}")
                if it.get("source"):
                    lines.append(f"  Source: {it['source']}")
                lines.append("")

        # Add retired items section if any
        retired = [it for it in items if it.get("status") == "retired"]
        if retired:
            lines.append("=" * 48)
            lines.append("RETIRED / ARCHIVED HEURISTICS")
            lines.append("=" * 48)
            lines.append("")
            for it in retired:
                lines.append(f"[{it['id']}] {it['title']} (RETIRED)")
                lines.append(f"  Reason: {it.get('retirement_reason', 'Superseded or stale')}")
                lines.append("")

        self.md_path.write_text("\n".join(lines), encoding="utf-8")

    def list_workflows(
        self,
        category: Optional[str] = None,
        status: Optional[str] = "active",
        search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Returns filtered list of workflows."""
        items = self._load_json()
        results = []

        for it in items:
            if status and it.get("status") != status:
                continue
            if category and category.lower() != "all" and it.get("category") != category.lower():
                continue
            if search:
                q = search.lower()
                text_to_search = f"{it.get('id', '')} {it.get('title', '')} {it.get('trigger', '')} {it.get('move', '')}".lower()
                if q not in text_to_search:
                    continue
            results.append(it)

        return results

    def get_workflow(self, wf_id: str) -> Optional[Dict[str, Any]]:
        items = self._load_json()
        clean_id = wf_id.strip().upper().replace("[", "").replace("]", "")
        for it in items:
            if it.get("id", "").upper() == clean_id:
                return it
        return None

    def record_workflow(
        self,
        title: str,
        trigger: str,
        move: str,
        category: str = "protocol",
        why: str = "",
        source: str = "",
        created_by: str = "Agent",
        custom_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Adds a new workflow rule to the living cabinet."""
        items = self._load_json()
        now_str = datetime.now().isoformat()

        cat_prefix = {
            "meta": "WF-M",
            "shape": "WF-S",
            "speed": "WF-P",
            "self_monitoring": "WF-X",
            "posture": "WF-T",
            "protocol": "WF-R",
            "custom": "WF-C"
        }.get(category.lower(), "WF-R")

        if custom_id:
            wf_id = custom_id.upper().replace("[", "").replace("]", "")
        else:
            # Calculate next sequence number for this prefix
            existing_nums = []
            for it in items:
                curr_id = it.get("id", "")
                if curr_id.startswith(cat_prefix):
                    num_part = curr_id[len(cat_prefix):]
                    if num_part.isdigit():
                        existing_nums.append(int(num_part))
            next_num = (max(existing_nums) + 1) if existing_nums else 1
            wf_id = f"{cat_prefix}{next_num}"

        new_entry = {
            "id": wf_id,
            "title": title.strip(),
            "category": category.lower(),
            "trigger": trigger.strip(),
            "move": move.strip(),
            "why": why.strip(),
            "source": source.strip(),
            "status": "active",
            "fire_count": 1,
            "last_fired_at": now_str,
            "created_by": created_by,
            "created_at": now_str,
            "updated_at": now_str
        }

        # Check for duplicate ID
        updated = False
        for idx, it in enumerate(items):
            if it.get("id") == wf_id:
                items[idx] = new_entry
                updated = True
                break

        if not updated:
            items.append(new_entry)

        self._save_json(items)
        self.sync_to_markdown()
        return new_entry

    def amend_workflow(self, wf_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Updates fields of an existing workflow."""
        items = self._load_json()
        clean_id = wf_id.strip().upper().replace("[", "").replace("]", "")
        target = None

        for idx, it in enumerate(items):
            if it.get("id", "").upper() == clean_id:
                for k, v in updates.items():
                    if k != "id":
                        it[k] = v
                it["updated_at"] = datetime.now().isoformat()
                items[idx] = it
                target = it
                break

        if target:
            self._save_json(items)
            self.sync_to_markdown()
        return target

    def record_fire(self, wf_id: str) -> Optional[Dict[str, Any]]:
        """Increments fire_count and updates last_fired_at timestamp."""
        items = self._load_json()
        clean_id = wf_id.strip().upper().replace("[", "").replace("]", "")
        target = None

        for idx, it in enumerate(items):
            if it.get("id", "").upper() == clean_id:
                it["fire_count"] = it.get("fire_count", 0) + 1
                it["last_fired_at"] = datetime.now().isoformat()
                items[idx] = it
                target = it
                break

        if target:
            self._save_json(items)
        return target

    def retire_workflow(self, wf_id: str, reason: str = "Superseded or stale") -> Optional[Dict[str, Any]]:
        """Retires a workflow heuristic from active rotation."""
        return self.amend_workflow(wf_id, {
            "status": "retired",
            "retirement_reason": reason,
            "retired_at": datetime.now().isoformat()
        })

    def reactivate_workflow(self, wf_id: str) -> Optional[Dict[str, Any]]:
        """Reactivates a retired workflow."""
        return self.amend_workflow(wf_id, {
            "status": "active",
            "reactivated_at": datetime.now().isoformat()
        })

    def get_groundskeeper_health(self) -> Dict[str, Any]:
        """
        Calculates health metrics for The Cabinet:
        - Total workflows & breakdown by status/category
        - Stale heuristics detection (inactive > 45 days or 0 fires)
        - Bloat warnings if active heuristics exceed optimal capacity (25)
        """
        items = self._load_json()
        active_items = [it for it in items if it.get("status") == "active"]
        retired_items = [it for it in items if it.get("status") == "retired"]

        categories = {}
        for it in active_items:
            cat = it.get("category", "protocol")
            categories[cat] = categories.get(cat, 0) + 1

        # Check staleness
        stale_candidates = []
        now = datetime.now()
        for it in active_items:
            last_fired = it.get("last_fired_at")
            if not last_fired:
                stale_candidates.append(it["id"])
                continue
            try:
                dt = datetime.fromisoformat(last_fired)
                if (now - dt).days > 45:
                    stale_candidates.append(it["id"])
            except Exception:
                pass

        bloat_risk = len(active_items) > 25
        recommendations = []
        if bloat_risk:
            recommendations.append(f"Active workflows ({len(active_items)}) exceeds lean target (25). Consider retiring non-firing items.")
        if stale_candidates:
            recommendations.append(f"{len(stale_candidates)} heuristics have had no recorded fire in >45 days: {', '.join(stale_candidates[:5])}")

        return {
            "status": "healthy" if not bloat_risk else "advisory",
            "total_count": len(items),
            "active_count": len(active_items),
            "retired_count": len(retired_items),
            "categories": categories,
            "stale_count": len(stale_candidates),
            "stale_ids": stale_candidates,
            "bloat_risk": bloat_risk,
            "recommendations": recommendations,
            "cabinet_path": str(self.cabinet_dir),
            "last_synced": datetime.now().isoformat()
        }


_CABINET_INSTANCE: Optional[CabinetManager] = None


def get_cabinet_manager() -> CabinetManager:
    global _CABINET_INSTANCE
    if _CABINET_INSTANCE is None:
        _CABINET_INSTANCE = CabinetManager()
    return _CABINET_INSTANCE
