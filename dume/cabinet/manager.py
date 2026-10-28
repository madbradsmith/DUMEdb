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

    def auto_harvest_rules_from_transcript(self, transcript_path: Optional[Path] = None) -> List[Dict[str, Any]]:
        """
        Scans the active conversation transcript.jsonl for operator-decreed rules and
        automatically mints them into The Cabinet and commits them to DUMEdb LMDB unit-record storage.
        Detects:
        - Terminology replacements ('replace X with Y', 'use X instead of Y', 'don't say X, say Y')
        - Explicit rules/laws/invariants/decisions ('rule: ...', 'decision: ...', 'invariant: ...')
        - Imperatives ('always ...', 'never ...')
        - Project policies ('from now on ...', 'going forward ...')
        - Commercial & Pricing constants ('license price is ...')
        """
        if not transcript_path:
            try:
                from dume.odometer import get_latest_transcript_path
                t_str = get_latest_transcript_path()
                if t_str and Path(t_str).exists():
                    transcript_path = Path(t_str)
            except Exception:
                pass

        if not transcript_path or not transcript_path.exists():
            return []

        minted = []
        items = self._load_json()
        existing_moves = [it.get("move", "").lower() for it in items]

        def _is_known(text: str) -> bool:
            clean = text.lower().strip()
            for em in existing_moves:
                if clean in em or em in clean:
                    return True
            return False

        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                for line in f:
                    step = json.loads(line)
                    if step.get("type") == "USER_INPUT":
                        content = step.get("content", "")
                        for l in content.splitlines():
                            l_clean = l.strip()
                            if not l_clean or len(l_clean) < 10:
                                continue

                            # Skip pure user requests asking to build harvester
                            if "rules in chat need to be identified" in l_clean.lower():
                                continue

                            entry_candidate = None

                            # Pattern 1: Terminology replacements ('remove/replace X with Y', 'use X instead of Y')
                            m_replace = re.search(
                                r"(?:we\s+decided\s+to\s+)?(?:remove|replace)\s+(?:the\s+term\s+)?['\"]?([^'\"\s]+)['\"]?\s+(?:with|and\s+replace\s+it\s+with)\s+['\"]?([^'\"\s.,]+)['\"]?",
                                l_clean,
                                re.IGNORECASE
                            )
                            if m_replace:
                                old_term, new_term = m_replace.group(1), m_replace.group(2)
                                title = f"TERMINOLOGY RULE: {new_term.upper()} OVER {old_term.upper()}"
                                move = f"Always use the term '{new_term}'. NEVER use the term '{old_term}'. The term '{old_term}' is strictly retired and forbidden."
                                if not _is_known(move):
                                    entry_candidate = {
                                        "title": title,
                                        "trigger": f"When writing or outputting terminology regarding {new_term}",
                                        "move": move,
                                        "category": "nomenclature",
                                        "why": f"Operator explicitly decreed replacing '{old_term}' with '{new_term}'"
                                    }

                            # Pattern 2: Explicit prefix ('rule:', 'law:', 'invariant:', 'decision:')
                            if not entry_candidate:
                                m_rule = re.search(r"^(?:rule|law|invariant|decision):\s*(.+)$", l_clean, re.IGNORECASE)
                                if m_rule:
                                    rule_text = m_rule.group(1).strip()
                                    title = f"RULE: {rule_text[:45]}"
                                    if not _is_known(rule_text):
                                        entry_candidate = {
                                            "title": title,
                                            "trigger": "Always active constraint",
                                            "move": rule_text,
                                            "category": "protocol",
                                            "why": "Operator explicitly prefixed rule"
                                        }

                            # Pattern 3: Imperatives ('always ...', 'never ...')
                            if not entry_candidate:
                                m_imp = re.search(r"^(?:from now on,?\s+|make sure to\s+|going forward,?\s+)?(always|never)\s+(.+?)(?:\.|$)", l_clean, re.IGNORECASE)
                                if m_imp:
                                    mode, action = m_imp.group(1).upper(), m_imp.group(2).strip()
                                    if len(action) > 12:
                                        title = f"INVARIANT: {mode} {action[:40]}"
                                        move = f"{mode}: {action}"
                                        if not _is_known(move):
                                            entry_candidate = {
                                                "title": title,
                                                "trigger": "Session invariant constraint",
                                                "move": move,
                                                "category": "protocol",
                                                "why": f"Operator decreed imperative {mode}"
                                            }

                            # Pattern 4: Policies ('from now on ...', 'going forward ...')
                            if not entry_candidate:
                                m_fno = re.search(r"^(?:from now on|going forward),?\s*(.+?)(?:\.|$)", l_clean, re.IGNORECASE)
                                if m_fno:
                                    action = m_fno.group(1).strip()
                                    if len(action) > 12:
                                        title = f"POLICY: {action[:45]}"
                                        move = f"Policy (from now on): {action}"
                                        if not _is_known(move):
                                            entry_candidate = {
                                                "title": title,
                                                "trigger": "Active project policy",
                                                "move": move,
                                                "category": "protocol",
                                                "why": "Operator set forward policy"
                                            }

                            # Pattern 5: Agreed Decisions ('we decided to / that ...')
                            if not entry_candidate:
                                m_dec = re.search(r"(?:we\s+decided\s+(?:to|that))\s+(.+?)(?:\.|$)", l_clean, re.IGNORECASE)
                                if m_dec:
                                    action = m_dec.group(1).strip()
                                    if len(action) > 15:
                                        title = f"DECISION: {action[:45]}"
                                        move = f"Agreed decision: {action}"
                                        if not _is_known(move):
                                            entry_candidate = {
                                                "title": title,
                                                "trigger": "Project decision alignment",
                                                "move": move,
                                                "category": "protocol",
                                                "why": "Agreed decision recorded in chat"
                                            }

                            if entry_candidate:
                                entry = self.record_workflow(
                                    title=entry_candidate["title"],
                                    trigger=entry_candidate["trigger"],
                                    move=entry_candidate["move"],
                                    category=entry_candidate["category"],
                                    why=entry_candidate.get("why", ""),
                                    source="Auto-Harvested from Operator Chat",
                                    created_by="Cabinet Auto-Harvester"
                                )
                                minted.append(entry)
                                existing_moves.append(entry_candidate["move"].lower())

                                # Also commit to DUMEdb LMDB unit-record storage
                                try:
                                    import hashlib, uuid
                                    from dume.onboarding import get_storage_dir
                                    from dume.storage.lmdb_engine import DUMEMemoryEngine
                                    from dume.core.record import UnitRecord
                                    from dume.schema.dictionary import SchemaDictionary, OpcodeSpec

                                    storage_dir = get_storage_dir()
                                    engine = DUMEMemoryEngine(storage_dir)
                                    schema = SchemaDictionary()

                                    op = schema.get_opcode_by_name("OPERATOR_LAW_DIRECTIVE")
                                    if op is None:
                                        spec = OpcodeSpec(
                                            opcode=1030,
                                            name="OPERATOR_LAW_DIRECTIVE",
                                            description="Active Operator Law / Rule directive committed from chat",
                                            data_type="STRING_REF"
                                        )
                                        schema.register_opcode(spec, persist=True, is_custom=True)

                                    entity_bytes = uuid.uuid5(uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8"), "MadBrad-AG-01").bytes
                                    rule_payload = f"[{entry['id']}] {entry['title']}: {entry['move']}".encode("utf-8")
                                    payload_hash_int = int.from_bytes(hashlib.sha256(rule_payload).digest()[:8], byteorder="big", signed=True)

                                    rec = UnitRecord.create(
                                        entity_id=entity_bytes,
                                        opcode=1030,
                                        value=payload_hash_int,
                                        has_extension_payload=True,
                                        is_active=True
                                    )
                                    engine.put_record(rec, payload_bytes=rule_payload)
                                except Exception:
                                    pass
        except Exception:
            pass

        return minted


_CABINET_INSTANCE: Optional[CabinetManager] = None


def get_cabinet_manager() -> CabinetManager:
    global _CABINET_INSTANCE
    if _CABINET_INSTANCE is None:
        _CABINET_INSTANCE = CabinetManager()
    return _CABINET_INSTANCE
