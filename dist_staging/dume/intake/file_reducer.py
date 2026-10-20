import os
import csv
import io
import hashlib
import base64
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

ASSETS_DIR = Path.home() / ".dume" / "assets"


def ensure_assets_dir() -> Path:
    """Ensures ~/.dume/assets directory exists."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    return ASSETS_DIR


def save_asset(file_bytes: bytes, filename: str) -> Tuple[str, str]:
    """
    Computes SHA256 hash of file_bytes and saves asset as ~/.dume/assets/<hash>.<ext>.
    Returns (asset_hash, asset_path).
    """
    ensure_assets_dir()
    sha256_hash = hashlib.sha256(file_bytes).hexdigest()
    ext = Path(filename).suffix.lower() or ".bin"
    asset_filename = f"{sha256_hash}{ext}"
    asset_path = ASSETS_DIR / asset_filename

    if not asset_path.exists():
        with open(asset_path, "wb") as f:
            f.write(file_bytes)

    return sha256_hash, str(asset_path)


class FileReducer:
    """
    Multimodal File Reducer & Parser.
    Extracts compact, deterministic KEY=VALUE register candidates from uploaded files.
    """

    @staticmethod
    def reduce_csv(file_bytes: bytes, filename: str, prefix: str = "") -> List[Dict[str, str]]:
        """Parses CSV files into deterministic register pairs."""
        results = []
        try:
            text = file_bytes.decode("utf-8", errors="replace")
            reader = list(csv.reader(io.StringIO(text)))

            clean_name = Path(filename).stem.upper().replace(" ", "_")
            results.append({"key": f"{prefix}FILE_NAME", "value": clean_name})
            results.append({"key": f"{prefix}ROW_COUNT", "value": str(max(0, len(reader) - 1))})

            if reader and len(reader) > 0:
                headers = [h.strip() for h in reader[0] if h.strip()]
                if headers:
                    results.append({"key": f"{prefix}COLUMNS", "value": ",".join(headers[:10])})

                if len(reader) > 1:
                    first_row = reader[1]
                    for idx, header in enumerate(headers[:6]):
                        if idx < len(first_row) and first_row[idx].strip():
                            clean_hdr = header.upper().replace(" ", "_")
                            results.append({"key": f"{prefix}SAMPLE_{clean_hdr}", "value": first_row[idx].strip()})
        except Exception as e:
            results.append({"key": f"{prefix}PARSE_ERROR", "value": str(e)})

        return results

    @staticmethod
    def reduce_xlsx(file_bytes: bytes, filename: str, prefix: str = "") -> List[Dict[str, str]]:
        """Parses Excel (.xlsx) spreadsheets into deterministic register pairs."""
        results = []
        clean_name = Path(filename).stem.upper().replace(" ", "_")
        results.append({"key": f"{prefix}FILE_NAME", "value": clean_name})

        try:
            import openpyxl
            wb = openpyxl.load_workbook(filename=io.BytesIO(file_bytes), read_only=True, data_only=True)
            sheet_names = wb.sheetnames
            results.append({"key": f"{prefix}SHEET_NAMES", "value": ",".join(sheet_names[:5])})

            if sheet_names:
                sheet = wb[sheet_names[0]]
                rows = list(sheet.iter_rows(values_only=True))
                results.append({"key": f"{prefix}ROW_COUNT", "value": str(max(0, len(rows) - 1))})

                if rows and len(rows) > 0:
                    headers = [str(cell).strip() for cell in rows[0] if cell is not None and str(cell).strip()]
                    if headers:
                        results.append({"key": f"{prefix}COLUMNS", "value": ",".join(headers[:10])})

                    if len(rows) > 1:
                        first_row = rows[1]
                        for idx, header in enumerate(headers[:6]):
                            if idx < len(first_row) and first_row[idx] is not None:
                                clean_hdr = str(header).upper().replace(" ", "_")
                                results.append({"key": f"{prefix}SAMPLE_{clean_hdr}", "value": str(first_row[idx]).strip()})
        except ImportError:
            # Fallback for lightweight zip/xml parsing if openpyxl is missing
            try:
                import zipfile
                import xml.etree.ElementTree as ET
                with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                    sheets = [f for f in z.namelist() if f.startswith("xl/worksheets/sheet")]
                    results.append({"key": f"{prefix}SHEETS_COUNT", "value": str(len(sheets))})
            except Exception as ex:
                results.append({"key": f"{prefix}XLSX_REDUCER", "value": f"openpyxl required: {ex}"})
        except Exception as e:
            results.append({"key": f"{prefix}PARSE_ERROR", "value": str(e)})

        return results

    @staticmethod
    def reduce_image(
        file_bytes: bytes,
        filename: str,
        prefix: str = "",
        synthesizer: Any = None,
        entity_config: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, str]]:
        """Parses document/scene images into clean operational KEY=VALUE registers."""
        results = []
        clean_name = Path(filename).stem.upper().replace(" ", "_")
        results.append({"key": f"{prefix}FILE_NAME", "value": clean_name})
        results.append({"key": f"{prefix}FILE_SIZE_KB", "value": str(round(len(file_bytes) / 1024, 1))})

        b64_data = base64.b64encode(file_bytes).decode("utf-8")
        ext = Path(filename).suffix.lower().lstrip(".")
        mime_type = f"image/{ext if ext in ('png', 'jpeg', 'webp') else 'png'}"

        if synthesizer and entity_config:
            try:
                # Construct zero-shot OCR / operational vision prompt
                vision_prompt = (
                    f"Analyze this document/scene image ({filename}). Extract key operational facts, document metadata, "
                    "or operational labels. Return EXCLUSIVELY valid KEY=VALUE lines, one per line (e.g. DIRECTOR=Ridley Scott)."
                )
                res = synthesizer.generate(
                    prompt=vision_prompt,
                    system_prompt="You are a strict multimodal document parser. Output only KEY=VALUE pairs, one per line.",
                    provider=entity_config.get("provider"),
                    api_key=entity_config.get("api_key"),
                    model_name=entity_config.get("model_name"),
                    endpoint_url=entity_config.get("endpoint_url")
                )
                for line in res.splitlines():
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        k_clean = k.strip().upper().replace(" ", "_")
                        v_clean = v.strip().strip('"').strip("'")
                        if k_clean and v_clean:
                            results.append({"key": f"{prefix}{k_clean}", "value": v_clean})
            except Exception as e:
                results.append({"key": f"{prefix}VISION_ERROR", "value": str(e)})
        else:
            # Fallback metadata extraction
            results.append({"key": f"{prefix}IMAGE_TYPE", "value": ext.upper()})

        return results

    @staticmethod
    def reduce_media(file_bytes: bytes, filename: str, prefix: str = "") -> List[Dict[str, str]]:
        """Parses video/audio container header metadata."""
        results = []
        clean_name = Path(filename).stem.upper().replace(" ", "_")
        ext = Path(filename).suffix.upper().lstrip(".")
        results.append({"key": f"{prefix}FILE_NAME", "value": clean_name})
        results.append({"key": f"{prefix}MEDIA_TYPE", "value": ext})
        results.append({"key": f"{prefix}FILE_SIZE_MB", "value": str(round(len(file_bytes) / (1024 * 1024), 2))})
        return results

    @classmethod
    def reduce_file(
        cls,
        file_bytes: bytes,
        filename: str,
        prefix: str = "",
        synthesizer: Any = None,
        entity_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Unified file reduction router. Saves raw file as asset and extracts candidate register pairs.
        """
        asset_hash, asset_path = save_asset(file_bytes, filename)
        ext = Path(filename).suffix.lower()
        pfx = prefix.upper().strip()
        if pfx and not pfx.endswith("_"):
            pfx += "_"

        registers = [
            {"key": f"{pfx}ASSET_HASH", "value": asset_hash},
            {"key": f"{pfx}ASSET_PATH", "value": asset_path}
        ]

        if ext == ".csv":
            registers.extend(cls.reduce_csv(file_bytes, filename, prefix=pfx))
        elif ext in (".xlsx", ".xls"):
            registers.extend(cls.reduce_xlsx(file_bytes, filename, prefix=pfx))
        elif ext in (".png", ".jpg", ".jpeg", ".webp"):
            registers.extend(cls.reduce_image(file_bytes, filename, prefix=pfx, synthesizer=synthesizer, entity_config=entity_config))
        elif ext in (".mp4", ".mov", ".avi", ".mkv", ".mp3", ".wav"):
            registers.extend(cls.reduce_media(file_bytes, filename, prefix=pfx))
        else:
            clean_name = Path(filename).stem.upper().replace(" ", "_")
            registers.append({"key": f"{pfx}FILE_NAME", "value": clean_name})

        # Deduplicate keys while preserving order
        seen_keys = set()
        unique_registers = []
        for reg in registers:
            if reg["key"] not in seen_keys:
                seen_keys.add(reg["key"])
                unique_registers.append(reg)

        return {
            "filename": filename,
            "asset_hash": asset_hash,
            "asset_path": asset_path,
            "registers": unique_registers
        }
