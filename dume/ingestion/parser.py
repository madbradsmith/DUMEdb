import time
import hashlib
from typing import Dict, Any, Tuple, Optional, Union, List

from dume.core.record import UnitRecord, FLAG_ACTIVE, FLAG_EXTENSION_PAYLOAD
from dume.schema.dictionary import SchemaDictionary, OpcodeSpec


class IngestionError(Exception):
    """Raised when an incoming event violates DUME schema constraints or opcodes."""
    pass


class ConstrainedIngestionEngine:
    """
    Constrained Ingestion Engine.
    Ensures zero invalid opcodes or corrupt memory states are committed to DUME.
    """
    def __init__(self, schema_dict: SchemaDictionary):
        self.schema_dict = schema_dict

    def validate_and_parse(
        self,
        entity_id: Union[bytes, str],
        opcode_identifier: Union[int, str],
        raw_value: Any,
        timestamp: Optional[int] = None
    ) -> Tuple[UnitRecord, Optional[bytes]]:
        """
        Parses and validates a proposed state register update against the SchemaDictionary.
        Returns a tuple of (UnitRecord, optional_payload_bytes).
        """
        # Resolve opcode
        if isinstance(opcode_identifier, str):
            opcode = self.schema_dict.get_opcode_by_name(opcode_identifier)
            if opcode is None:
                raise IngestionError(f"Unknown opcode name: '{opcode_identifier}'")
        else:
            opcode = opcode_identifier
            if not (0 <= opcode <= 0xFFFF):
                raise IngestionError(f"Opcode out of uint16 range: {opcode}")

        spec = self.schema_dict.get_spec(opcode)
        if spec is None:
            raise IngestionError(f"Unregistered opcode ID: {opcode}")

        dt = spec.data_type.upper()
        payload_bytes: Optional[bytes] = None
        has_ext_payload = False
        final_val: Union[int, float] = 0

        # Type checking & constraint parsing
        if dt == "BOOL":
            if isinstance(raw_value, bool):
                final_val = 1 if raw_value else 0
            elif isinstance(raw_value, (int, str)):
                s = str(raw_value).strip().lower()
                final_val = 1 if s in ("1", "true", "yes", "on", "t") else 0
            else:
                raise IngestionError(f"Invalid boolean value for opcode {spec.name}: {raw_value}")

        elif dt == "ENUM":
            if isinstance(raw_value, int):
                if raw_value not in spec.enum_values:
                    raise IngestionError(f"Invalid enum int '{raw_value}' for opcode {spec.name}. Allowed: {list(spec.enum_values.keys())}")
                final_val = raw_value
            elif isinstance(raw_value, str):
                matched_id = None
                str_val = raw_value.strip().upper()
                for k, v in spec.enum_values.items():
                    if v.upper() == str_val:
                        matched_id = k
                        break
                if matched_id is None:
                    raise IngestionError(f"Invalid enum string '{raw_value}' for opcode {spec.name}. Allowed: {list(spec.enum_values.values())}")
                final_val = matched_id
            else:
                raise IngestionError(f"Invalid enum value type for opcode {spec.name}: {type(raw_value)}")

        elif dt == "INT":
            try:
                final_val = int(raw_value)
            except (ValueError, TypeError):
                raise IngestionError(f"Invalid integer value for opcode {spec.name}: {raw_value}")

        elif dt == "FLOAT":
            try:
                final_val = float(raw_value)
            except (ValueError, TypeError):
                raise IngestionError(f"Invalid float value for opcode {spec.name}: {raw_value}")

        elif dt == "STRING_REF":
            # Off-bus extension pointer
            if not isinstance(raw_value, str):
                raw_value = str(raw_value)
            payload_bytes = raw_value.encode("utf-8")
            has_ext_payload = True
            # Compute 64-bit integer payload hash for value field
            hash_8 = hashlib.blake2b(payload_bytes, digest_size=8).digest()
            final_val = int.from_bytes(hash_8, byteorder='big', signed=True)

        else:
            raise IngestionError(f"Unsupported data type '{dt}' in schema for opcode {spec.name}")

        # Construct UnitRecord
        rec = UnitRecord.create(
            entity_id=entity_id,
            opcode=opcode,
            value=final_val,
            timestamp=timestamp,
            is_active=True,
            has_extension_payload=has_ext_payload,
            schema_version=self.schema_dict.version
        )

        return rec, payload_bytes

    parse_mutation = validate_and_parse


StateParser = ConstrainedIngestionEngine

