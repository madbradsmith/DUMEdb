import json
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Union, List
from dataclasses import dataclass, field, asdict

from dume.core.record import UnitRecord, uuid_to_hex


@dataclass
class OpcodeSpec:
    opcode: int
    name: str
    description: str
    data_type: str  # "INT", "FLOAT", "BOOL", "ENUM", "STRING_REF"
    enum_values: Dict[int, str] = field(default_factory=dict)
    unit: Optional[str] = None
    is_auto: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "opcode": self.opcode,
            "name": self.name,
            "description": self.description,
            "data_type": self.data_type,
            "enum_values": {str(k): str(v) for k, v in self.enum_values.items()},
            "unit": self.unit,
            "is_auto": self.is_auto
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OpcodeSpec":
        raw_enum = data.get("enum_values", {})
        enum_vals = {int(k): str(v) for k, v in raw_enum.items()}
        return cls(
            opcode=int(data["opcode"]),
            name=str(data["name"]),
            description=str(data.get("description", "")),
            data_type=str(data.get("data_type", "INT")),
            enum_values=enum_vals,
            unit=data.get("unit"),
            is_auto=bool(data.get("is_auto", False))
        )


DEFAULT_OPCODES: List[OpcodeSpec] = [
    OpcodeSpec(
        opcode=1001,
        name="USER_LOCALE",
        description="User preferred language/locale enum ID",
        data_type="ENUM",
        enum_values={1: "en-US", 2: "es-ES", 3: "ja-JP", 4: "de-DE", 5: "zh-CN"}
    ),
    OpcodeSpec(
        opcode=1002,
        name="UI_THEME",
        description="User interface visual theme",
        data_type="ENUM",
        enum_values={0: "SYSTEM", 1: "DARK", 2: "LIGHT", 3: "HIGH_CONTRAST"}
    ),
    OpcodeSpec(
        opcode=1003,
        name="ACCOUNT_TIER",
        description="User subscription / permission tier level",
        data_type="ENUM",
        enum_values={1: "FREE", 2: "PRO", 3: "ENTERPRISE", 4: "ADMIN"}
    ),
    OpcodeSpec(
        opcode=1004,
        name="ACCOUNT_BALANCE_CENTS",
        description="Account credit balance in cents",
        data_type="INT",
        unit="cents"
    ),
    OpcodeSpec(
        opcode=1005,
        name="TEMPERATURE_PREFERENCE",
        description="Preferred temperature setting in degrees Celsius",
        data_type="FLOAT",
        unit="Celsius"
    ),
    OpcodeSpec(
        opcode=1006,
        name="NOTIFICATION_ENABLED",
        description="Global notification status flag",
        data_type="BOOL"
    ),
    OpcodeSpec(
        opcode=1007,
        name="PROFILE_BIO_PAYLOAD_REF",
        description="Off-bus extension pointer hash to full text bio blob",
        data_type="STRING_REF"
    ),
]


class SchemaDictionary:
    """
    Independent Schema & Concept Dictionary with Dynamic Runtime Mutation & Disk Persistence.
    Translates raw 32-byte binary opcodes and state values to human-readable text.
    """
    def __init__(
        self,
        version: int = 1,
        opcodes: Optional[List[OpcodeSpec]] = None,
        storage_path: Optional[Union[str, Path]] = None
    ):
        self.version = version
        self.storage_path = Path(storage_path) if storage_path else Path("data/registered_schemas.json")
        self._opcodes: Dict[int, OpcodeSpec] = {}
        self._name_to_opcode: Dict[str, int] = {}
        self._custom_opcodes: Dict[int, OpcodeSpec] = {}

        # 1. Register base default opcodes without persistence
        specs = opcodes if opcodes is not None else DEFAULT_OPCODES
        for spec in specs:
            self.register_opcode(spec, persist=False, is_custom=False)

        # 2. Load custom registered opcodes from disk if available
        self.load_from_disk()

    def register_opcode(
        self,
        spec: OpcodeSpec,
        persist: bool = True,
        is_custom: bool = True
    ) -> OpcodeSpec:
        """
        Registers a new opcode specification in memory and atomically persists to disk.
        Raises ValueError on duplicate opcode ID or duplicate opcode Name collisions.
        """
        if not (0 <= spec.opcode <= 0xFFFF):
            raise ValueError(f"Opcode must fit in uint16 (0-65535), got {spec.opcode}")

        clean_name = spec.name.strip().upper()
        if not clean_name:
            raise ValueError("Opcode name cannot be empty")

        if spec.opcode in self._opcodes:
            existing = self._opcodes[spec.opcode]
            if existing.name.upper() != clean_name:
                raise ValueError(f"Opcode ID collision: {spec.opcode} is already registered as '{existing.name}'")

        if clean_name in self._name_to_opcode:
            existing_id = self._name_to_opcode[clean_name]
            if existing_id != spec.opcode:
                existing_spec = self._opcodes.get(existing_id)
                if existing_spec and existing_spec.is_auto:
                    self._opcodes.pop(existing_id, None)
                    self._custom_opcodes.pop(existing_id, None)
                else:
                    raise ValueError(f"Opcode Name collision: '{spec.name}' is already registered with Opcode ID {existing_id}")

        self._opcodes[spec.opcode] = spec
        self._name_to_opcode[clean_name] = spec.opcode

        if is_custom:
            self._custom_opcodes[spec.opcode] = spec
            if persist:
                self.save_to_disk()

        return spec

    def get_next_available_opcode(self) -> int:
        """Calculates and returns the next unused integer opcode ID (starting from 2001)."""
        auto_keys = [k for k in self._opcodes.keys() if 2000 <= k <= 2999]
        if not auto_keys:
            return 2001
        return max(auto_keys) + 1

    def get_next_available_custom_opcode(self) -> int:
        """Calculates and returns the next unused custom integer opcode ID (starting from 3001)."""
        custom_keys = [k for k in self._opcodes.keys() if 3000 <= k <= 3999]
        if not custom_keys:
            return 3001
        return max(custom_keys) + 1

    def promote_auto_opcode(self, opcode_id: int) -> OpcodeSpec:
        """Promotes an auto-discovered [AUTO] opcode (2xxx) to a permanent registered schema."""
        if opcode_id not in self._opcodes:
            raise ValueError(f"Opcode ID {opcode_id} not found in SchemaDictionary")
        spec = self._opcodes[opcode_id]
        spec.is_auto = False
        self._custom_opcodes[opcode_id] = spec
        self.save_to_disk()
        return spec

    def get_spec(self, opcode: int) -> Optional[OpcodeSpec]:
        return self._opcodes.get(opcode)

    def get_opcode_by_name(self, name: str) -> Optional[int]:
        return self._name_to_opcode.get(name.strip().upper())

    def get_all_specs(self) -> List[OpcodeSpec]:
        return list(self._opcodes.values())

    def format_value(self, opcode: int, record: UnitRecord) -> Any:
        spec = self.get_spec(opcode)
        if not spec:
            return record.float_value if record.is_float_value else record.value

        dt = spec.data_type.upper()
        if dt == "FLOAT" or record.is_float_value:
            return record.float_value
        elif dt == "BOOL":
            return bool(record.value)
        elif dt == "ENUM":
            return spec.enum_values.get(record.value, f"UNKNOWN_ENUM_{record.value}")
        elif dt == "STRING_REF":
            return f"PAYLOAD_HASH:0x{record.value & 0xFFFFFFFFFFFFFFFF:016x}"
        else:
            return record.value

    def decode_record(self, record: UnitRecord) -> Dict[str, Any]:
        """Decodes a 32-byte raw UnitRecord into a rich human-readable dictionary."""
        spec = self.get_spec(record.opcode)
        opcode_name = spec.name if spec else f"UNKNOWN_OPCODE_{record.opcode}"
        human_val = self.format_value(record.opcode, record)

        return {
            "entity_id": uuid_to_hex(record.entity_id),
            "opcode": record.opcode,
            "opcode_name": opcode_name,
            "raw_value": record.value,
            "human_value": human_val,
            "timestamp": record.timestamp,
            "flags": {
                "active": record.is_active,
                "has_extension_payload": record.has_extension_payload,
                "is_float": record.is_float_value,
                "raw_hex": f"0x{record.flags:04x}"
            },
            "description": spec.description if spec else "Unregistered Opcode",
            "schema_version": (record.flags >> 8) & 0xFF
        }

    def save_to_disk(self):
        """Atomically saves all custom registered opcodes to JSON disk file."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": self.version,
            "custom_opcodes": [spec.to_dict() for spec in self._custom_opcodes.values()]
        }
        temp_path = self.storage_path.with_suffix(".tmp")
        with temp_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        temp_path.replace(self.storage_path)

    def load_from_disk(self):
        """Loads custom registered opcodes from disk if storage file exists."""
        if not self.storage_path.exists():
            return
        try:
            with self.storage_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data.get("custom_opcodes", []):
                spec = OpcodeSpec.from_dict(item)
                self.register_opcode(spec, persist=False, is_custom=True)
        except Exception as err:
            print(f"[SchemaDictionary] Warning loading custom schemas from {self.storage_path}: {err}")

    def save_yaml(self, filepath: Union[str, Path]):
        path = Path(filepath)
        data = {
            "version": self.version,
            "opcodes": [spec.to_dict() for spec in self._opcodes.values()]
        }
        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False)

    @classmethod
    def load_yaml(cls, filepath: Union[str, Path]) -> "SchemaDictionary":
        path = Path(filepath)
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        version = data.get("version", 1)
        specs = [OpcodeSpec.from_dict(item) for item in data.get("opcodes", [])]
        return cls(version=version, opcodes=specs)
