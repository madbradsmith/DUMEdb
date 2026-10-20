import time
from typing import Dict, Any, List, Optional, Callable, Tuple, Union

from dume.core.record import UnitRecord, uuid_to_hex
from dume.schema.dictionary import SchemaDictionary
from dume.storage.lmdb_engine import DUMEMemoryEngine
from dume.ingestion.parser import ConstrainedIngestionEngine, IngestionError


class ScribeCommitter:
    """
    Direct DUMEdb Committer.
    Commits validated 32-byte unit records to LMDB out-of-band and notifies real-time subscribers.
    """
    def __init__(self, memory_engine: DUMEMemoryEngine, schema_dict: SchemaDictionary):
        self.memory_engine = memory_engine
        self.schema_dict = schema_dict
        self.ingestion_engine = ConstrainedIngestionEngine(schema_dict)
        self.listeners: List[Callable[[Dict[str, Any]], None]] = []

    def register_listener(self, callback: Callable[[Dict[str, Any]], None]):
        """Register a callback for real-time WebSocket / UI mutation events."""
        self.listeners.append(callback)

    def commit_mutation(
        self,
        entity_id: str,
        opcode_identifier: Union[int, str],
        raw_value: Any,
        timestamp: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Validates candidate mutation and performs atomic LMDB commit.
        Returns decoded mutation event dict or None if invalid.
        """
        try:
            rec, payload = self.ingestion_engine.validate_and_parse(
                entity_id=entity_id,
                opcode_identifier=opcode_identifier,
                raw_value=raw_value,
                timestamp=timestamp
            )

            # Atomic commit to active_state (O(1)) and history_log
            self.memory_engine.put_record(rec, payload_bytes=payload)
            decoded = self.schema_dict.decode_record(rec)

            event = {
                "type": "MUTATION_COMMIT",
                "timestamp": rec.timestamp,
                "entity_id": decoded["entity_id"],
                "opcode": rec.opcode,
                "opcode_name": decoded["opcode_name"],
                "human_value": decoded["human_value"],
                "raw_hex": rec.pack().hex(),
                "decoded": decoded
            }

            # Notify real-time listeners (e.g. WebSocket inspector)
            for listener in self.listeners:
                try:
                    listener(event)
                except Exception:
                    pass

            return event
        except IngestionError as e:
            # Invalid candidate, log and reject cleanly without corrupting DB
            return None
