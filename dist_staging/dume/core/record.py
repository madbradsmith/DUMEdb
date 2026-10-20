import struct
import time
import os
import uuid
from dataclasses import dataclass
from typing import Union, Tuple, Optional, Any

# Bitfield Flag Definitions
FLAG_ACTIVE = 0x0001               # Bit 0: 1 = Active, 0 = Tombstoned / Deleted
FLAG_EXTENSION_PAYLOAD = 0x0002    # Bit 1: 1 = Value is off-bus payload reference hash/offset
FLAG_FLOAT_VALUE = 0x0004          # Bit 2: 1 = Value bytes represent IEEE 754 float64
FLAG_SCHEMA_VERSION_MASK = 0xFF00  # High byte: Schema version (0..255)

RECORD_STRUCT_FORMAT = "!16sHqIH"  # 16B Entity UUID, 2B Opcode, 8B Value, 4B Timestamp, 2B Flags
RECORD_SIZE_BYTES = 32

assert struct.calcsize(RECORD_STRUCT_FORMAT) == RECORD_SIZE_BYTES, f"Struct size must be exactly 32 bytes, got {struct.calcsize(RECORD_STRUCT_FORMAT)}"

def generate_uuidv7_bytes(ts_ms: Optional[int] = None) -> bytes:
    """
    Generate a 16-byte UUIDv7 timestamp-ordered identifier.
    48 bits = timestamp (ms), 12 bits = counter/rand, 64 bits = rand.
    """
    if ts_ms is None:
        ts_ms = int(time.time() * 1000)
    
    # 48-bit timestamp
    ts_bytes = (ts_ms & 0xFFFFFFFFFFFF).to_bytes(6, byteorder='big')
    
    # 10 bytes random
    rand_bytes = os.urandom(10)
    
    # Set version (7) in byte 6 high nibble
    ver_byte = (rand_bytes[0] & 0x0F) | 0x70
    
    # Set variant (rfc4122) in byte 8 high 2 bits
    var_byte = (rand_bytes[2] & 0x3F) | 0x80
    
    return ts_bytes + bytes([ver_byte, rand_bytes[1], var_byte]) + rand_bytes[3:]

def uuid_to_hex(uuid_bytes: bytes) -> str:
    """Format 16-byte UUID into standard hex string representation."""
    return str(uuid.UUID(bytes=uuid_bytes))

def hex_to_uuid_bytes(hex_str: str) -> bytes:
    """Convert hex string UUID representation back to 16-byte buffer."""
    return uuid.UUID(hex_str).bytes


@dataclass(frozen=True)
class UnitRecord:
    """
    Fixed 32-Byte Packed Binary State Unit Record.
    """
    entity_id: bytes        # 16 bytes UUIDv7
    opcode: int             # uint16 (0..65535)
    value: int              # int64 (signed 64-bit int or raw bit pattern)
    timestamp: int          # uint32 (epoch seconds or micros offset)
    flags: int              # uint16 (bitfield)

    def __post_init__(self):
        if len(self.entity_id) != 16:
            raise ValueError(f"entity_id must be exactly 16 bytes, got {len(self.entity_id)}")
        if not (0 <= self.opcode <= 0xFFFF):
            raise ValueError(f"opcode must be uint16 (0..65535), got {self.opcode}")
        if not (-0x8000_0000_0000_0000 <= self.value <= 0x7FFF_FFFF_FFFF_FFFF):
            raise ValueError(f"value must fit in int64, got {self.value}")
        if not (0 <= self.timestamp <= 0xFFFF_FFFF):
            raise ValueError(f"timestamp must be uint32 (0..4294967295), got {self.timestamp}")
        if not (0 <= self.flags <= 0xFFFF):
            raise ValueError(f"flags must be uint16, got {self.flags}")

    @property
    def is_active(self) -> bool:
        return bool(self.flags & FLAG_ACTIVE)

    @property
    def has_extension_payload(self) -> bool:
        return bool(self.flags & FLAG_EXTENSION_PAYLOAD)

    @property
    def is_float_value(self) -> bool:
        return bool(self.flags & FLAG_FLOAT_VALUE)

    @property
    def float_value(self) -> float:
        """Decode value field as double precision float64 if FLAG_FLOAT_VALUE is set."""
        val_bytes = self.value.to_bytes(8, byteorder='big', signed=True)
        return struct.unpack("!d", val_bytes)[0]

    def pack(self) -> bytes:
        """Serialize UnitRecord into deterministic 32-byte binary representation."""
        return struct.pack(
            RECORD_STRUCT_FORMAT,
            self.entity_id,
            self.opcode,
            self.value,
            self.timestamp,
            self.flags
        )

    @classmethod
    def unpack(cls, data: Union[bytes, memoryview]) -> "UnitRecord":
        """Zero-copy unpack UnitRecord from 32-byte binary buffer or memoryview."""
        if len(data) != RECORD_SIZE_BYTES:
            raise ValueError(f"Expected {RECORD_SIZE_BYTES} bytes, got {len(data)}")
        
        entity_id, opcode, value, timestamp, flags = struct.unpack(RECORD_STRUCT_FORMAT, data)
        return cls(
            entity_id=entity_id,
            opcode=opcode,
            value=value,
            timestamp=timestamp,
            flags=flags
        )

    @classmethod
    def create(
        cls,
        entity_id: Union[bytes, str],
        opcode: int,
        value: Union[int, float],
        timestamp: Optional[int] = None,
        is_active: bool = True,
        has_extension_payload: bool = False,
        schema_version: int = 1
    ) -> "UnitRecord":
        """Factory helper to create a valid UnitRecord with automatic flag construction."""
        if isinstance(entity_id, str):
            entity_bytes = hex_to_uuid_bytes(entity_id)
        else:
            entity_bytes = entity_id

        if timestamp is None:
            timestamp = int(time.time()) & 0xFFFFFFFF

        flags = 0
        if is_active:
            flags |= FLAG_ACTIVE
        if has_extension_payload:
            flags |= FLAG_EXTENSION_PAYLOAD

        if isinstance(value, float):
            flags |= FLAG_FLOAT_VALUE
            # Pack float to int64 bit pattern
            val_bytes = struct.pack("!d", value)
            int_val = int.from_bytes(val_bytes, byteorder='big', signed=True)
        else:
            int_val = int(value)

        flags |= ((schema_version & 0xFF) << 8)

        return cls(
            entity_id=entity_bytes,
            opcode=opcode,
            value=int_val,
            timestamp=timestamp,
            flags=flags
        )
