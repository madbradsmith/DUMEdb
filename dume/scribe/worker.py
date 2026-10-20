import re
import asyncio
import logging
import time
from typing import List, Dict, Any, Tuple, Optional, Union

from dume.session.dispatcher import SessionDispatcher, TurnPayload
from dume.scribe.committer import ScribeCommitter
from dume.schema.dictionary import SchemaDictionary, OpcodeSpec

logger = logging.getLogger("dume.scribe.worker")


class ScribeWorker:
    """
    Constrained Background Scribe Worker with Autonomous Schema Discovery.
    Asynchronously consumes turns from the queue, evaluates state mutations out-of-band,
    auto-discovers novel domain schemas, and commits valid 32-byte records without impacting chat streaming.
    """
    def __init__(
        self,
        dispatcher: SessionDispatcher,
        committer: ScribeCommitter,
        schema_dict: SchemaDictionary
    ):
        self.dispatcher = dispatcher
        self.committer = committer
        self.schema_dict = schema_dict
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def start(self):
        """Start the background consumer loop on the active asyncio event loop."""
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._worker_loop())

    async def stop(self):
        """Gracefully stop the background worker task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _worker_loop(self):
        while self._running:
            try:
                # Wait for next turn payload from queue with timeout for clean shutdown
                try:
                    payload: TurnPayload = await asyncio.wait_for(self.dispatcher.queue.get(), timeout=0.2)
                except asyncio.TimeoutError:
                    continue
                
                # Process turn out-of-band
                self.process_turn(payload)
                self.dispatcher.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in ScribeWorker loop: {e}")

    def deduplicate_or_mint_opcode(
        self,
        proposed_name: str,
        inferred_type: str = "INT",
        description: str = ""
    ) -> Tuple[int, bool]:
        """
        Semantic Deduplication & Auto-Minting Engine.
        1. Normalizes proposed name.
        2. Checks for exact match or semantic token overlap against existing schema opcodes.
        3. If existing match found, returns (opcode_id, False).
        4. If no match found, mints next available opcode, persists to disk, and returns (new_opcode_id, True).
        """
        clean_name = re.sub(r'[^A-Z0-9_]', '_', proposed_name.upper().strip())
        clean_name = re.sub(r'_+', '_', clean_name).strip('_')

        # 1. Exact match check
        existing_id = self.schema_dict.get_opcode_by_name(clean_name)
        if existing_id is not None:
            return (existing_id, False)

        # 2. Semantic Token Overlap Deduplication Check
        # Extract core domain tokens (e.g. ['CAMERA', 'LENS'] from CAMERA_LENS_FOCAL_LENGTH_MM)
        proposed_tokens = set(t for t in clean_name.split('_') if len(t) > 2)
        
        for spec in self.schema_dict.get_all_specs():
            spec_tokens = set(t for t in spec.name.upper().split('_') if len(t) > 2)
            # If at least 2 major tokens overlap (e.g. CAMERA and LENS), map to existing opcode!
            overlap = proposed_tokens.intersection(spec_tokens)
            if len(overlap) >= 2:
                return (spec.opcode, False)

        # 3. Mint new opcode
        new_opcode_id = self.schema_dict.get_next_available_opcode()
        spec = OpcodeSpec(
            opcode=new_opcode_id,
            name=clean_name,
            description=description or f"Auto-discovered state register for {clean_name}",
            data_type=inferred_type.upper(),
            is_auto=True
        )
        self.schema_dict.register_opcode(spec, persist=True)
        return (new_opcode_id, True)

    def extract_novel_facts(self, text: str) -> List[Dict[str, Any]]:
        """
        Extracts novel stateful key-value facts from conversational text using grammar patterns.
        """
        facts = []

        # Pattern 1: Camera lens focal length (e.g. "My primary camera lens is a 50mm prime", "Set camera lens to 35mm")
        lens_match = re.search(r"camera\s+lens(?:\s+is|\s+to|\s+focal\s+length)?\s+(?:a\s+)?(\d+)\s*mm", text, re.IGNORECASE)
        if lens_match:
            facts.append({
                "proposed_name": "CAMERA_LENS_FOCAL_LENGTH_MM",
                "inferred_type": "INT",
                "description": "Primary camera lens focal length in millimeters",
                "value": int(lens_match.group(1))
            })
            return facts

        # Pattern 2: Pomodoro / Focus session duration (e.g. "My focus duration is 25 minutes", "Set pomodoro to 30")
        pomo_match = re.search(r"(?:pomodoro|focus(?:\s+work|\s+session)?)\s+(?:duration|time)?\s+(?:is|to)?\s*(\d+)", text, re.IGNORECASE)
        if pomo_match:
            facts.append({
                "proposed_name": "POMODORO_DURATION_MINUTES",
                "inferred_type": "INT",
                "description": "User focus work session duration in minutes",
                "value": int(pomo_match.group(1))
            })
            return facts

        # Pattern 3: Generic "my <domain> is <numeric>" or "set my <domain> to <numeric>"
        generic_num_match = re.search(r"(?:my|set|change)\s+([a-z0-9_\s]{3,30})\s+(?:is|to)\s+(\d+)", text, re.IGNORECASE)
        if generic_num_match:
            domain_raw = generic_num_match.group(1).strip()
            val_num = int(generic_num_match.group(2))
            clean_name = re.sub(r'[^A-Z0-9_]', '_', domain_raw.upper())
            clean_name = re.sub(r'_+', '_', clean_name).strip('_')
            facts.append({
                "proposed_name": clean_name,
                "inferred_type": "INT",
                "description": f"Auto-discovered state register for {clean_name}",
                "value": val_num
            })

        return facts

    def process_turn(self, payload: TurnPayload) -> List[Dict[str, Any]]:
        """
        Evaluates turn text against SchemaDictionary predicates & Autonomous Discovery engine.
        Commits valid candidates and auto-minted opcodes to LMDB via ScribeCommitter.
        """
        text = f"{payload.user_text} {payload.agent_text}".strip().lower()
        entity_id = payload.entity_id
        timestamp = payload.timestamp

        candidates: List[Tuple[Union[int, str], Any]] = []

        # 1. Check UI_THEME
        if "light" in text and ("theme" in text or "mode" in text):
            candidates.append(("UI_THEME", "LIGHT"))
        elif "dark" in text and ("theme" in text or "mode" in text):
            candidates.append(("UI_THEME", "DARK"))
        elif "high contrast" in text:
            candidates.append(("UI_THEME", "HIGH_CONTRAST"))

        # 2. Check USER_LOCALE
        if "spanish" in text or "es-es" in text:
            candidates.append(("USER_LOCALE", "es-ES"))
        elif "japanese" in text or "ja-jp" in text:
            candidates.append(("USER_LOCALE", "ja-JP"))
        elif "german" in text or "de-de" in text:
            candidates.append(("USER_LOCALE", "de-DE"))
        elif "chinese" in text or "zh-cn" in text:
            candidates.append(("USER_LOCALE", "zh-CN"))
        elif "english" in text or "en-us" in text:
            candidates.append(("USER_LOCALE", "en-US"))

        # 3. Check ACCOUNT_TIER
        if "pro tier" in text or "pro account" in text or "upgrade to pro" in text:
            candidates.append(("ACCOUNT_TIER", "PRO"))
        elif "enterprise" in text:
            candidates.append(("ACCOUNT_TIER", "ENTERPRISE"))
        elif "admin" in text:
            candidates.append(("ACCOUNT_TIER", "ADMIN"))

        # 4. Check ACCOUNT_BALANCE_CENTS
        drop_match = re.search(r"(?:drop|lower|reduce|deduct)\s+(?:my\s+)?balance\s+by\s+(\d+)", text)
        set_balance_match = re.search(r"(?:set|change)\s+(?:my\s+)?balance\s+to\s+(\d+)", text)
        
        if drop_match:
            amount = int(drop_match.group(1))
            current_rec = self.committer.memory_engine.get_active_record(entity_id, 1004) # ACCOUNT_BALANCE_CENTS
            current_bal = current_rec.value if current_rec else 10000
            new_bal = max(0, current_bal - amount)
            candidates.append(("ACCOUNT_BALANCE_CENTS", new_bal))
        elif set_balance_match:
            amount = int(set_balance_match.group(1))
            candidates.append(("ACCOUNT_BALANCE_CENTS", amount))

        # 5. Check TEMPERATURE_PREFERENCE
        temp_match = re.search(r"temperature\s+(?:to\s+)?(\d+(?:\.\d+)?)", text)
        if temp_match:
            val = float(temp_match.group(1))
            candidates.append(("TEMPERATURE_PREFERENCE", val))

        # 6. Check NOTIFICATION_ENABLED
        if "enable notification" in text or "turn on notification" in text:
            candidates.append(("NOTIFICATION_ENABLED", True))
        elif "disable notification" in text or "turn off notification" in text:
            candidates.append(("NOTIFICATION_ENABLED", False))

        # 7. Autonomous Schema Discovery Pipeline (if no hardcoded rules matched)
        if not candidates:
            novel_facts = self.extract_novel_facts(text)
            for fact in novel_facts:
                opcode_id, is_new = self.deduplicate_or_mint_opcode(
                    proposed_name=fact["proposed_name"],
                    inferred_type=fact["inferred_type"],
                    description=fact["description"]
                )
                candidates.append((opcode_id, fact["value"]))

        # Commit candidate mutations with monotonic timestamps
        committed_events = []
        for i, (opcode_id, val) in enumerate(candidates):
            ts = (timestamp + i) & 0xFFFFFFFF if timestamp else (int(time.time()) + i) & 0xFFFFFFFF
            event = self.committer.commit_mutation(
                entity_id=entity_id,
                opcode_identifier=opcode_id,
                raw_value=val,
                timestamp=ts
            )
            if event:
                committed_events.append(event)

        return committed_events
