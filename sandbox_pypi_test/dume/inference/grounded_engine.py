from typing import List, Dict, Any, Optional, Union, Callable

from dume.core.record import UnitRecord, uuid_to_hex
from dume.schema.dictionary import SchemaDictionary
from dume.storage.lmdb_engine import DUMEMemoryEngine


class GroundedInferenceEngine:
    """
    Grounded Inference Core.
    Injects ultra-lean discrete state registers (<=50 tokens) into synthesis LLMs.
    """
    def __init__(self, memory_engine: DUMEMemoryEngine, schema_dict: SchemaDictionary):
        self.memory_engine = memory_engine
        self.schema_dict = schema_dict

    def build_register_context(self, entity_id: Union[bytes, str]) -> str:
        """
        Fetches active state registers from LMDB and formats an ultra-dense prompt register prefix.
        Target size: <= 50 tokens.
        """
        records = self.memory_engine.get_all_active_registers(entity_id)
        if not records:
            return ""

        hex_id = uuid_to_hex(records[0].entity_id) if records else str(entity_id)
        short_id = hex_id[:8]

        items = []
        for rec in records:
            spec = self.schema_dict.get_spec(rec.opcode)
            name = spec.name if spec else f"OP_{rec.opcode}"
            val = self.schema_dict.format_value(rec.opcode, rec)
            items.append(f"{name}={val}")

        registers_str = " | ".join(items)
        return f"[DUME_STATE entity={short_id}] {registers_str} [/DUME_STATE]"

    def format_grounded_prompt(
        self,
        entity_id: Union[bytes, str],
        user_prompt: str,
        history_entries: Optional[List[Any]] = None
    ) -> str:
        """
        Assembles grounded prompt combining discrete DUME register state ([DUME_STATE ...]),
        bounded conversation scratchpad history (up to K turns), and the current user query.
        """
        reg_ctx = self.build_register_context(entity_id)

        history_lines = []
        if history_entries:
            for turn in history_entries[:-1]:  # Exclude current turn if present in history list
                u_text = getattr(turn, 'user_text', '')
                a_text = getattr(turn, 'agent_text', '')
                if u_text:
                    history_lines.append(f"User: {u_text}")
                if a_text:
                    history_lines.append(f"Assistant: {a_text}")

        parts = []
        if reg_ctx:
            parts.append(reg_ctx)
        if history_lines:
            parts.append("\n".join(history_lines))
        parts.append(f"User: {user_prompt}\nAssistant:")

        return "\n\n".join(parts)

    def generate(
        self,
        entity_id: Union[bytes, str],
        user_prompt: str,
        llm_fn: Optional[Callable[[str], str]] = None,
        history_entries: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        """
        Executes grounded inference with deterministic state injection and bounded scratchpad context.
        """
        reg_ctx = self.build_register_context(entity_id)
        full_prompt = self.format_grounded_prompt(entity_id, user_prompt, history_entries)

        # Estimate token count (rough rule: 4 chars / token)
        reg_token_estimate = max(1, len(reg_ctx) // 4) if reg_ctx else 0

        if llm_fn:
            llm_response = llm_fn(full_prompt)
        else:
            # Deterministic Local Synthesizer Mock
            llm_response = f"Processed query for entity with active state context: {reg_ctx or 'None'}"

        return {
            "entity_id": uuid_to_hex(entity_id) if isinstance(entity_id, bytes) else entity_id,
            "register_context": reg_ctx,
            "register_token_count": reg_token_estimate,
            "full_prompt": full_prompt,
            "response": llm_response
        }
