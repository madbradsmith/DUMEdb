import re
import time
from typing import Dict, Any, List, Optional, Union, Tuple

from dume.core.record import UnitRecord, uuid_to_hex, hex_to_uuid_bytes
from dume.schema.dictionary import SchemaDictionary, OpcodeSpec
from dume.storage.lmdb_engine import DUMEMemoryEngine
from dume.ingestion.parser import ConstrainedIngestionEngine, IngestionError
from dume.scribe.committer import ScribeCommitter
from dume.session.context_manager import BoundedBufferManager


NOISE_KEYS = {
    "TODAY", "TOMORROW", "OVERWHELMED", "HELLO", "THANKS", "PLEASE",
    "SORRY", "OKAY", "SOMETHING", "HTTP", "HTTPS", "YESTERDAY",
    "REALLY", "ACTUALLY", "BECAUSE", "JUST", "ANYTHING", "EVERYTHING"
}

CANONICAL_KEY_REGEX = re.compile(r'^[A-Z0-9_]{3,32}$')


def is_canonical_key(key_name: str) -> bool:
    """
    Rule 3: Canonical Key Minting.
    Validates key name against strict uppercase alphanumeric snake_case (^[A-Z0-9_]{3,32}$).
    Rejects stop-words and conversational noise like TODAY, HTTPS, OVERWHELMED.
    """
    if not key_name or not CANONICAL_KEY_REGEX.match(key_name):
        return False
    if key_name in NOISE_KEYS:
        return False
    return True


def clean_extracted_value(val_str: str) -> str:
    """
    Cleans extracted value string:
    - Un-wraps markdown links: [text](url) -> url
    - Strips trailing table delimiters '|', quotes, and surrounding whitespace
    """
    if not val_str:
        return ""
    s = val_str.strip()

    # Clean markdown link [anchor](url) -> url
    md_link_match = re.search(r'\[.*?\]\((https?://[^\s)]+)\)', s)
    if md_link_match:
        s = md_link_match.group(1)
    else:
        # Generic markdown link [text](link)
        md_generic = re.search(r'\[.*?\]\((.*?)\)', s)
        if md_generic:
            s = md_generic.group(1)

    s = s.rstrip("|").strip().strip("'\"")
    return s


def extract_key_value_pairs(text: str) -> Dict[str, str]:
    """
    Refined Document Extraction Engine enforcing 3 core rules:
    1. Protocol Protection: Preserves 'http:' and 'https:' URLs intact without splitting on internal colons.
    2. Markdown Table Sanitization: Strips '|' delimiters and handles column 1 (key) & column 2 (val).
    3. Canonical Key Minting: Ensures keys strictly match ^[A-Z0-9_]{3,32}$, rejecting stop-words.
    """
    if not text:
        return {}

    results: Dict[str, str] = {}
    lines = text.splitlines()
    num_lines = len(lines)
    i = 0

    while i < num_lines:
        line = lines[i]
        raw_line = line.strip()
        if not raw_line or raw_line.startswith("#"):
            i += 1
            continue

        # Rule 2: Markdown Table Sanitization
        if "|" in raw_line:
            # Skip Markdown table separator rows like '|---|---|' or ':-:|:-:'
            if re.match(r'^[\s|:\-]+$', raw_line):
                i += 1
                continue

            # Skip the table header row if followed by an alignment separator line (e.g. | :--- | :--- | or |---|---|)
            if i + 1 < num_lines:
                next_line = lines[i + 1].strip()
                if "|" in next_line and re.match(r'^[\s|:\-]+$', next_line):
                    i += 1
                    continue

            cells = [c.strip() for c in raw_line.split("|") if c.strip()]
            if len(cells) >= 2:
                raw_key = cells[0]
                raw_val = cells[1]

                clean_key = re.sub(r'[^A-Za-z0-9_]', '_', raw_key).upper()
                clean_key = re.sub(r'_+', '_', clean_key).strip('_')

                if is_canonical_key(clean_key):
                    cleaned_v = clean_extracted_value(raw_val)
                    if cleaned_v:
                        results[clean_key] = cleaned_v
                i += 1
                continue

        # Non-table lines: extract key-value using colon/equals/is with protocol protection
        _extract_pair_from_string(raw_line, results)
        i += 1

    return results


def _extract_pair_from_string(text_line: str, results: Dict[str, str]):
    """
    Extracts KEY=VAL, KEY: VAL, or KEY is VAL from text string.
    Rule 1: Protocol Protection for http:// and https:// URLs.
    Rule 3: Canonical Key Minting validation against NOISE_KEYS.
    Supports complex quoted strings, JSON payloads, and code syntax.
    """
    # 1. Line-level direct assignment match (handles complex quoted strings, JSON blobs, etc.)
    line_match = re.match(
        r'^\s*([A-Za-z0-9_]{3,32})\s*(?:=|\s+(?:is|IS)\s+|(?:(?<!http)(?<!https):))\s*(.+)$',
        text_line,
        re.IGNORECASE
    )
    if line_match:
        raw_key = line_match.group(1).strip()
        raw_val = line_match.group(2).strip()

        clean_key = re.sub(r'[^A-Za-z0-9_]', '_', raw_key).upper()
        clean_key = re.sub(r'_+', '_', clean_key).strip('_')

        if is_canonical_key(clean_key):
            cleaned_v = clean_extracted_value(raw_val)
            if cleaned_v:
                results[clean_key] = cleaned_v
                return

    # 2. Fallback regex for inline occurrences in sentence text
    pattern = re.compile(
        r'(?:^|[\s,;])([A-Za-z0-9_]{3,32})\s*(?:=|\s+(?:is|IS)\s+|(?:(?<!http)(?<!https):))\s*[\'"]?([^\r\n\'";]+[\'"]?)',
        re.IGNORECASE
    )

    for match in pattern.finditer(text_line):
        raw_key = match.group(1).strip()
        raw_val = match.group(2).strip()

        clean_key = re.sub(r'[^A-Za-z0-9_]', '_', raw_key).upper()
        clean_key = re.sub(r'_+', '_', clean_key).strip('_')

        if is_canonical_key(clean_key):
            cleaned_v = clean_extracted_value(raw_val)
            if cleaned_v:
                results[clean_key] = cleaned_v


class BatchIngestionEngine:
    """
    Batch Ingestion & Dynamic Register Hydration Engine.
    Ingests key-value state mappings, auto-mints 2xxx opcodes for novel fields,
    executes atomic multi-record LMDB commits, and flushes session context buffers.
    """
    def __init__(
        self,
        memory_engine: DUMEMemoryEngine,
        schema_dict: SchemaDictionary,
        scribe_committer: Optional[ScribeCommitter] = None,
        context_manager: Optional[BoundedBufferManager] = None
    ):
        self.memory_engine = memory_engine
        self.schema_dict = schema_dict
        self.scribe_committer = scribe_committer
        self.context_manager = context_manager
        self.ingestion_engine = ConstrainedIngestionEngine(schema_dict)

    def process_batch(
        self,
        entity_id: Union[bytes, str],
        registers: Dict[str, Any],
        flush_scratchpad: bool = False,
        timestamp: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Processes a dictionary of candidate registers for the given entity.
        Performs single-transaction LMDB commit and optional scratchpad flush.
        """
        if isinstance(entity_id, bytes):
            canonical_uuid_bytes = entity_id
            entity_hex = uuid_to_hex(entity_id)
        else:
            entity_hex = entity_id
            canonical_uuid_bytes = hex_to_uuid_bytes(entity_id)

        ts = timestamp if timestamp is not None else (int(time.time()) & 0xFFFFFFFF)
        records_to_commit: List[Tuple[UnitRecord, Optional[bytes]]] = []

        if isinstance(registers, list):
            registers = {r["key"]: r["value"] for r in registers if isinstance(r, dict) and "key" in r}

        new_opcodes_registered = False

        for key, raw_val in registers.items():
            clean_name = re.sub(r'[^A-Za-z0-9_]', '_', key.strip()).upper()
            clean_name = re.sub(r'_+', '_', clean_name).strip('_')

            # Rule 3: Canonical Key Minting & Conversational Fragment Rejection
            if not is_canonical_key(clean_name):
                print(f"[BatchIngestionEngine] Rejecting key '{key}' -> '{clean_name}': Fails canonical key validation (^[A-Z0-9_]{{3,32}}$ or stop-word).")
                continue

            opcode = self.schema_dict.get_opcode_by_name(clean_name)
            if opcode is None:
                # Novel candidate opcode: auto-mint in 2xxx range
                opcode = self.schema_dict.get_next_available_opcode()
                dt = "INT"
                if isinstance(raw_val, bool):
                    dt = "BOOL"
                elif isinstance(raw_val, (int, float)):
                    dt = "FLOAT" if isinstance(raw_val, float) or "." in str(raw_val) else "INT"
                elif isinstance(raw_val, str):
                    s_lower = raw_val.strip().lower()
                    if s_lower in ("true", "false", "yes", "no"):
                        dt = "BOOL"
                    else:
                        try:
                            f = float(raw_val)
                            dt = "FLOAT" if "." in raw_val else "INT"
                        except ValueError:
                            # Strings containing path separators, spaces, symbols, or length > 24 -> STRING_REF
                            if any(c in str(raw_val) for c in ("/", "\\", "\n", " ", ":", ".", "-", "_")) or len(str(raw_val)) > 24:
                                dt = "STRING_REF"
                            else:
                                dt = "ENUM"

                spec = OpcodeSpec(
                    opcode=opcode,
                    name=clean_name,
                    description=f"Auto-registered via batch ingestion for {clean_name}",
                    data_type=dt,
                    is_auto=True
                )
                if dt == "ENUM":
                    spec.enum_values = {1: str(raw_val)}

                self.schema_dict.register_opcode(spec, persist=False, is_custom=True)
                new_opcodes_registered = True

            cleaned_value = clean_extracted_value(str(raw_val)) if isinstance(raw_val, str) else raw_val

            # Dynamically expand auto-minted enum values if a novel enum string arrives
            existing_spec = self.schema_dict.get_spec_by_name(clean_name)
            if existing_spec and existing_spec.data_type == "ENUM" and existing_spec.is_auto:
                allowed_vals = [str(v).lower() for v in (existing_spec.enum_values or {}).values()]
                if str(cleaned_value).lower() not in allowed_vals:
                    next_idx = max(existing_spec.enum_values.keys(), default=0) + 1 if existing_spec.enum_values else 1
                    existing_spec.enum_values[next_idx] = str(cleaned_value)
                    self.schema_dict.register_opcode(existing_spec, persist=False, is_custom=True)
                    new_opcodes_registered = True

            try:
                rec, payload_bytes = self.ingestion_engine.validate_and_parse(
                    entity_id=canonical_uuid_bytes,
                    opcode_identifier=opcode,
                    raw_value=cleaned_value,
                    timestamp=ts
                )
                records_to_commit.append((rec, payload_bytes))
            except IngestionError as err:
                print(f"[BatchIngestionEngine] Warning skipping invalid key '{key}': {err}")

        if new_opcodes_registered:
            self.schema_dict.save_to_disk()

        # Atomic commit in a single write transaction
        if records_to_commit:
            self.memory_engine.put_records_batch(records_to_commit)

            # Notify listeners (e.g., WebSocket inspector UI)
            if self.scribe_committer:
                for rec, payload in records_to_commit:
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
                    for listener in self.scribe_committer.listeners:
                        try:
                            listener(event)
                        except Exception:
                            pass

        # Optional scratchpad buffer flush
        if flush_scratchpad and self.context_manager:
            self.context_manager.flush_session_scratchpad(entity_hex)

        decoded_records = [self.schema_dict.decode_record(rec) for rec, _ in records_to_commit]
        return {
            "status": "success",
            "entity_id": entity_hex,
            "committed_count": len(records_to_commit),
            "records": decoded_records,
            "flushed_scratchpad": flush_scratchpad,
            "timestamp": ts
        }
