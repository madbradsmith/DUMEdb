import re
import hashlib
from typing import Dict, Any, List, Tuple, Optional, Union
from dume.core.record import UnitRecord, uuid_to_hex, hex_to_uuid_bytes
from dume.schema.dictionary import SchemaDictionary, OpcodeSpec
from dume.storage.lmdb_engine import DUMEMemoryEngine


from dume.scribe.ingest import is_canonical_key, extract_key_value_pairs


class InlineDirectiveParser:
    """
    Inline Directive Interceptor & Entity Tag Extractor.
    Extracts inline [ENTITY:name] tags, !set KEY=VALUE directives, and !flush commands from prompt text.
    """

    # Match [ENTITY:entity_name] anywhere in text
    ENTITY_TAG_REGEX = re.compile(r'\[ENTITY:\s*([^\]]+)\]', re.IGNORECASE)

    # Match !set KEY=VALUE anywhere in text (stops at space, another directive, or end of line)
    SET_DIRECTIVE_REGEX = re.compile(r'!set\s+([A-Za-z0-9_]{3,32})\s*=\s*(\S+)', re.IGNORECASE)

    # Match !flush command anywhere in text
    FLUSH_DIRECTIVE_REGEX = re.compile(r'!flush\b', re.IGNORECASE)

    # Match !intake command anywhere in text
    INTAKE_DIRECTIVE_REGEX = re.compile(r'!intake\b', re.IGNORECASE)

    # Match !bootstrap [pack_name] command anywhere in text
    BOOTSTRAP_DIRECTIVE_REGEX = re.compile(r'!bootstrap(?:\s+([A-Za-z0-9_\-]+))?', re.IGNORECASE)

    @classmethod
    def extract_entity_tag(cls, text: str) -> Tuple[str, Optional[str]]:
        """
        Extracts [ENTITY:entity_name] tag if present.
        Returns (cleaned_text, entity_name_or_None).
        """
        if not text:
            return text, None

        match = cls.ENTITY_TAG_REGEX.search(text)
        if not match:
            return text, None

        entity_name = match.group(1).strip()
        cleaned_text = cls.ENTITY_TAG_REGEX.sub('', text)
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
        return cleaned_text, entity_name

    @classmethod
    def parse_and_clean_directives(cls, text: str) -> Tuple[str, List[Dict[str, str]], bool, bool, Optional[str]]:
        """
        Parses !set KEY=VALUE, !flush, !intake, and !bootstrap from prompt text.
        Enforces Rule 3 (Canonical Key Minting ^[A-Z0-9_]{3,32}$) on !set directives.
        Strips directives from text and collapses redundant whitespace.
        Returns (clean_text, set_directives, has_flush, has_intake, bootstrap_pack).
        """
        if not text:
            return text, [], False, False, None

        set_directives = []
        for match in cls.SET_DIRECTIVE_REGEX.finditer(text):
            key = match.group(1).strip().upper()
            val = match.group(2).strip()
            if is_canonical_key(key):
                set_directives.append({"key": key, "value": val})

        has_flush = bool(cls.FLUSH_DIRECTIVE_REGEX.search(text))
        has_intake = bool(cls.INTAKE_DIRECTIVE_REGEX.search(text))

        bootstrap_match = cls.BOOTSTRAP_DIRECTIVE_REGEX.search(text)
        bootstrap_pack = None
        if bootstrap_match:
            bootstrap_pack = bootstrap_match.group(1).strip() if bootstrap_match.group(1) else ""

        # Strip directives from text
        clean_text = cls.SET_DIRECTIVE_REGEX.sub('', text)
        clean_text = cls.FLUSH_DIRECTIVE_REGEX.sub('', clean_text)
        clean_text = cls.INTAKE_DIRECTIVE_REGEX.sub('', clean_text)
        clean_text = cls.BOOTSTRAP_DIRECTIVE_REGEX.sub('', clean_text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()

        return clean_text, set_directives, has_flush, has_intake, bootstrap_pack

    @classmethod
    def execute_set_directives(
        cls,
        directives: List[Dict[str, str]],
        canonical_uuid_bytes: bytes,
        memory_engine: DUMEMemoryEngine,
        schema_dict: SchemaDictionary
    ) -> List[UnitRecord]:
        """
        Commits parsed !set key-value directives to LMDB.
        Auto-registers novel opcodes into 2xxx range if not present in SchemaDictionary.
        """
        committed_records = []
        for d in directives:
            clean_name = d["key"]
            value = d["value"]

            opcode = schema_dict.get_opcode_by_name(clean_name)
            spec: Optional[OpcodeSpec] = None

            if opcode is not None:
                spec = schema_dict.get_spec(opcode)
            else:
                # Novel schema discovery for inline directive
                opcode = schema_dict.get_next_available_opcode()
                dt = "INT"
                if value.lower() in ("true", "false"):
                    dt = "BOOL"
                else:
                    try:
                        float(value)
                        dt = "FLOAT" if "." in value else "INT"
                    except ValueError:
                        dt = "ENUM"

                spec = OpcodeSpec(
                    opcode=opcode,
                    name=clean_name,
                    description=f"Auto-registered via inline directive for {clean_name}",
                    data_type=dt,
                    is_auto=True
                )
                if dt == "ENUM":
                    spec.enum_values = {1: value}
                schema_dict.register_opcode(spec, persist=True, is_custom=True)

            dt = spec.data_type if spec else "INT"
            rec: UnitRecord

            if dt == "FLOAT":
                try:
                    f_val = float(value)
                except Exception:
                    f_val = 0.0
                rec = UnitRecord.create_float(
                    entity_id=canonical_uuid_bytes,
                    opcode=opcode,
                    float_val=f_val
                )
            elif dt == "BOOL":
                b_val = 1 if value.lower() in ("1", "true", "yes", "on") else 0
                rec = UnitRecord.create(
                    entity_id=canonical_uuid_bytes,
                    opcode=opcode,
                    value=b_val
                )
            elif dt == "ENUM":
                enum_map = spec.enum_values if spec else {}
                matched_code: Optional[int] = None
                val_str = str(value).strip().upper()

                for k, v in enum_map.items():
                    if str(v).strip().upper() == val_str:
                        matched_code = k
                        break

                if matched_code is None:
                    try:
                        matched_code = int(value)
                    except Exception:
                        matched_code = max(enum_map.keys(), default=0) + 1
                        if spec:
                            spec.enum_values[matched_code] = str(value)
                            schema_dict.save_to_disk()

                rec = UnitRecord.create(
                    entity_id=canonical_uuid_bytes,
                    opcode=opcode,
                    value=matched_code
                )
            else:
                try:
                    i_val = int(value)
                except Exception:
                    i_val = 0
                rec = UnitRecord.create(
                    entity_id=canonical_uuid_bytes,
                    opcode=opcode,
                    value=i_val
                )

            memory_engine.put_record(rec)
            committed_records.append(rec)

        return committed_records
