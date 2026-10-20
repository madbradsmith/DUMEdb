import lmdb
import struct
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Generator, Union, Any

from dume.core.record import (
    UnitRecord, RECORD_SIZE_BYTES, RECORD_STRUCT_FORMAT,
    FLAG_ACTIVE, hex_to_uuid_bytes, uuid_to_hex
)


_ENV_CACHE: Dict[str, lmdb.Environment] = {}


class DUMEMemoryEngine:
    """
    Hardware-Aligned Zero-Copy Storage Substrate backed by LMDB (mmap).
    Manages active_state (O(1) latest registers), history_log (O(K) timeline), and payload_store.
    """
    def __init__(self, db_path: Union[str, Path], map_size: int = 10 * 1024 * 1024 * 1024):  # 10GB default map
        self.db_path = Path(db_path).resolve()
        self.db_path.mkdir(parents=True, exist_ok=True)
        self.map_size = map_size
        self._init_env()

    def _init_env(self):
        key = str(self.db_path)
        if key in _ENV_CACHE:
            self.env = _ENV_CACHE[key]
        else:
            self.env = lmdb.open(
                key,
                map_size=self.map_size,
                max_dbs=5,
                sync=True,
                metasync=True,
                readahead=True,
                writemap=False
            )
            _ENV_CACHE[key] = self.env

        # Open named databases
        self.db_active = self.env.open_db(b"active_state")
        self.db_history = self.env.open_db(b"history_log", dupsort=True)
        self.db_payloads = self.env.open_db(b"payload_store")

    def _ensure_open(self):
        try:
            self.env.stat()
        except Exception:
            key = str(self.db_path)
            _ENV_CACHE.pop(key, None)
            self._init_env()

    def close(self):
        key = str(self.db_path)
        _ENV_CACHE.pop(key, None)
        try:
            self.env.close()
        except Exception:
            pass

    def __enter__(self):
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # -------------------------------------------------------------------------
    # Core Write Operations (State Mutation)
    # -------------------------------------------------------------------------

    def put_record(self, record: UnitRecord, payload_bytes: Optional[bytes] = None) -> bool:
        return self.put_records_batch([(record, payload_bytes)])

    def put_records_batch(self, items: List[Tuple[UnitRecord, Optional[bytes]]]) -> bool:
        """
        Store multiple state records in a single high-throughput LMDB write transaction.
        """
        self._ensure_open()
        with self.env.begin(write=True) as txn:
            for record, payload_bytes in items:
                raw_record = record.pack()
                active_key = record.entity_id + struct.pack("!H", record.opcode)
                history_key = record.entity_id + struct.pack("!IH", record.timestamp, record.opcode)

                if record.is_active:
                    txn.put(active_key, raw_record, db=self.db_active)
                else:
                    try:
                        txn.delete(active_key, db=self.db_active)
                    except Exception:
                        pass

                txn.put(history_key, raw_record, db=self.db_history)

                if payload_bytes and record.has_extension_payload:
                    payload_hash = record.value.to_bytes(8, byteorder='big', signed=True)
                    txn.put(payload_hash, payload_bytes, db=self.db_payloads)

        return True

    def tombstone_register(self, entity_id: Union[bytes, str], opcode: int, timestamp: Optional[int] = None) -> bool:
        """
        Soft-delete (tombstone) an active state register by putting an inactive record.
        """
        entity_bytes = hex_to_uuid_bytes(entity_id) if isinstance(entity_id, str) else entity_id
        current = self.get_active_record(entity_bytes, opcode)
        
        val = current.value if current else 0
        tombstone_rec = UnitRecord.create(
            entity_id=entity_bytes,
            opcode=opcode,
            value=val,
            timestamp=timestamp,
            is_active=False
        )
        return self.put_record(tombstone_rec)

    # -------------------------------------------------------------------------
    # Core Read Operations (Zero-Copy mmap Reads)
    # -------------------------------------------------------------------------

    def get_active_record(self, entity_id: Union[bytes, str], opcode: int) -> Optional[UnitRecord]:
        """
        O(1) zero-copy state register lookup. Returns UnitRecord if present and active.
        """
        self._ensure_open()
        entity_bytes = hex_to_uuid_bytes(entity_id) if isinstance(entity_id, str) else entity_id
        active_key = entity_bytes + struct.pack("!H", opcode)

        with self.env.begin(db=self.db_active, write=False, buffers=True) as txn:
            buf = txn.get(active_key)
            if buf is None:
                return None
            record = UnitRecord.unpack(bytes(buf))
            return record if record.is_active else None

    def get_all_active_registers(self, entity_id: Union[bytes, str]) -> List[UnitRecord]:
        """
        Retrieve all active state registers for a given entity_id in microsecond scan time.
        """
        self._ensure_open()
        entity_bytes = hex_to_uuid_bytes(entity_id) if isinstance(entity_id, str) else entity_id
        records = []

        with self.env.begin(db=self.db_active, write=False, buffers=True) as txn:
            cursor = txn.cursor()
            if cursor.set_range(entity_bytes):
                for key, val in cursor:
                    key_bytes = bytes(key)
                    if not key_bytes.startswith(entity_bytes):
                        break
                    rec = UnitRecord.unpack(bytes(val))
                    if rec.is_active:
                        records.append(rec)
        return records

    def get_history(self, entity_id: Union[bytes, str], limit: int = 100) -> List[UnitRecord]:
        """
        Retrieve chronological history audit log for a given entity (newest first).
        """
        self._ensure_open()
        entity_bytes = hex_to_uuid_bytes(entity_id) if isinstance(entity_id, str) else entity_id
        history = []

        with self.env.begin(db=self.db_history, write=False, buffers=True) as txn:
            cursor = txn.cursor()
            next_prefix = entity_bytes[:-1] + bytes([entity_bytes[-1] + 1])
            if cursor.set_range(next_prefix):
                has_key = cursor.prev()
            else:
                has_key = cursor.last()

            while has_key:
                key_bytes = bytes(cursor.key())
                if not key_bytes.startswith(entity_bytes):
                    break
                history.append(UnitRecord.unpack(bytes(cursor.value())))
                if len(history) >= limit:
                    break
                has_key = cursor.prev()

        return history

    def get_payload(self, payload_hash: bytes) -> Optional[bytes]:
        """Fetch off-bus extension payload by hash."""
        self._ensure_open()
        with self.env.begin(db=self.db_payloads, write=False) as txn:
            val = txn.get(payload_hash)
            if val is None and len(payload_hash) == 16:
                val = txn.get(payload_hash[:8])
            return bytes(val) if val else None

    def get_payload_text(self, record_value: int) -> Optional[str]:
        """Convenience helper to fetch and decode UTF-8 STRING_REF text by record value."""
        payload_bytes = self.get_payload(record_value.to_bytes(8, byteorder='big', signed=True))
        return payload_bytes.decode("utf-8") if payload_bytes else None

    def get_all_entity_ids(self) -> List[str]:
        """Scan active_state LMDB database and return list of all distinct hex entity UUID strings."""
        self._ensure_open()
        entity_ids = set()
        with self.env.begin(db=self.db_active, write=False, buffers=True) as txn:
            cursor = txn.cursor()
            for key, val in cursor:
                key_bytes = bytes(key)
                if len(key_bytes) >= 16:
                    entity_bytes = key_bytes[:16]
                    entity_ids.add(uuid_to_hex(entity_bytes))
        return sorted(list(entity_ids))

    def get_stats(self) -> Dict[str, Any]:
        """Returns storage environment statistics and total record counts."""
        self._ensure_open()
        with self.env.begin(write=False) as txn:
            active_stat = txn.stat(self.db_active)
            history_stat = txn.stat(self.db_history)
            payload_stat = txn.stat(self.db_payloads)

        return {
            "active_registers_count": active_stat["entries"],
            "history_records_count": history_stat["entries"],
            "extension_payloads_count": payload_stat["entries"],
            "map_size_bytes": self.env.info()["map_size"],
            "path": str(self.db_path)
        }

    def delete_entity(self, entity_id: Union[bytes, str]) -> Dict[str, int]:
        """
        Atomically purges all active registers and history audit records for a given entity_id.
        Returns dictionary containing active_deleted and history_deleted record counts.
        """
        self._ensure_open()
        entity_bytes = hex_to_uuid_bytes(entity_id) if isinstance(entity_id, str) else entity_id
        active_deleted = 0
        history_deleted = 0

        with self.env.begin(write=True) as txn:
            cursor = txn.cursor(db=self.db_active)
            for key, val in list(cursor):
                if bytes(key).startswith(entity_bytes):
                    txn.delete(key, db=self.db_active)
                    active_deleted += 1

            cursor = txn.cursor(db=self.db_history)
            for key, val in list(cursor):
                if bytes(key).startswith(entity_bytes):
                    txn.delete(key, db=self.db_history)
                    history_deleted += 1

        return {
            "active_deleted": active_deleted,
            "history_deleted": history_deleted
        }

