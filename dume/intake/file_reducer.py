import os
import csv
import io
import hashlib
import base64
import json
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

    @staticmethod
    def reduce_text(
        file_bytes: bytes,
        filename: str,
        prefix: str = "",
        synthesizer: Any = None,
        entity_config: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, str]]:
        """Parses plain text and Markdown files (.txt, .md, .markdown, .rst, .py, etc.)."""
        results = []
        clean_name = Path(filename).stem.upper().replace(" ", "_")
        text = file_bytes.decode("utf-8", errors="replace")
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        words = text.split()

        results.append({"key": f"{prefix}FILE_NAME", "value": clean_name})
        results.append({"key": f"{prefix}WORD_COUNT", "value": str(len(words))})
        results.append({"key": f"{prefix}LINE_COUNT", "value": str(len(lines))})

        # Extract markdown headings / chapter titles
        headings = []
        for line in lines:
            if line.startswith("#"):
                clean_h = line.lstrip("#").strip()
                if clean_h and len(clean_h) < 100:
                    headings.append(clean_h)
        for idx, h in enumerate(headings[:8]):
            results.append({"key": f"{prefix}SECTION_{idx + 1}", "value": h})

        # Extract colon-separated or bulleted key-value facts
        facts_count = 0
        for line in lines:
            if line.startswith("#"):
                continue
            if ":" in line and not line.startswith("http"):
                parts = line.split(":", 1)
                k_cand = parts[0].strip().lstrip("-* \t").upper().replace(" ", "_")
                v_cand = parts[1].strip()
                if 2 <= len(k_cand) <= 25 and 2 <= len(v_cand) <= 120 and not k_cand.startswith("<"):
                    results.append({"key": f"{prefix}{k_cand}", "value": v_cand})
                    facts_count += 1
                    if facts_count >= 12:
                        break

        # Zero-shot AI distillation if synthesizer is available
        if synthesizer and entity_config and len(words) > 40:
            try:
                sample_text = text[:3000] + "\n...\n" + text[-1500:] if len(text) > 4500 else text
                prompt = (
                    f"Analyze this document ({filename}). Extract up to 8 core operational facts, entities, rules, or character roles.\n"
                    "Return EXCLUSIVELY lines formatted as: KEY=VALUE (e.g. PROTAGONIST=Frank, RULES=Must commit on first pass)."
                )
                res = synthesizer.generate(
                    prompt=prompt,
                    system_prompt="You are a strict document fact reducer. Output only KEY=VALUE pairs, one per line.",
                    provider=entity_config.get("provider"),
                    api_key=entity_config.get("api_key"),
                    model_name=entity_config.get("model_name"),
                    endpoint_url=entity_config.get("endpoint_url")
                )
                for l in res.splitlines():
                    l = l.strip()
                    if "=" in l and not l.startswith("#"):
                        k, v = l.split("=", 1)
                        k_clean = k.strip().upper().replace(" ", "_")
                        v_clean = v.strip().strip('"\'')
                        if k_clean and v_clean:
                            results.append({"key": f"{prefix}{k_clean}", "value": v_clean})
            except Exception:
                pass

        return results

    @staticmethod
    def reduce_pdf(
        file_bytes: bytes,
        filename: str,
        prefix: str = "",
        synthesizer: Any = None,
        entity_config: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, str]]:
        """Parses Adobe PDF (.pdf) documents."""
        results = []
        clean_name = Path(filename).stem.upper().replace(" ", "_")
        results.append({"key": f"{prefix}FILE_NAME", "value": clean_name})
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            num_pages = len(reader.pages)
            results.append({"key": f"{prefix}PAGE_COUNT", "value": str(num_pages)})

            extracted = []
            for i in range(min(num_pages, 6)):
                page_text = reader.pages[i].extract_text() or ""
                if page_text:
                    extracted.append(page_text)
            sample_text = "\n".join(extracted)
            sub = FileReducer.reduce_text(sample_text.encode("utf-8"), filename, prefix=prefix, synthesizer=synthesizer, entity_config=entity_config)
            results.extend([r for r in sub if not r["key"].endswith("FILE_NAME")])
        except Exception as e:
            results.append({"key": f"{prefix}PDF_PARSE", "value": str(e)})
        return results

    @staticmethod
    def reduce_docx(
        file_bytes: bytes,
        filename: str,
        prefix: str = "",
        synthesizer: Any = None,
        entity_config: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, str]]:
        """Parses Microsoft Word (.docx) documents."""
        results = []
        clean_name = Path(filename).stem.upper().replace(" ", "_")
        results.append({"key": f"{prefix}FILE_NAME", "value": clean_name})
        try:
            import docx
            doc = docx.Document(io.BytesIO(file_bytes))
            paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            sample_text = "\n".join(paragraphs)
            sub = FileReducer.reduce_text(sample_text.encode("utf-8"), filename, prefix=prefix, synthesizer=synthesizer, entity_config=entity_config)
            results.extend([r for r in sub if not r["key"].endswith("FILE_NAME")])
        except Exception as e:
            results.append({"key": f"{prefix}DOCX_PARSE", "value": str(e)})
        return results

    @staticmethod
    def reduce_json_yaml(file_bytes: bytes, filename: str, prefix: str = "") -> List[Dict[str, str]]:
        """Parses structured JSON and YAML files."""
        results = []
        clean_name = Path(filename).stem.upper().replace(" ", "_")
        results.append({"key": f"{prefix}FILE_NAME", "value": clean_name})
        ext = Path(filename).suffix.lower()
        try:
            if ext == ".json":
                data = json.loads(file_bytes.decode("utf-8", errors="replace"))
            else:
                import yaml
                data = yaml.safe_load(file_bytes.decode("utf-8", errors="replace"))

            if isinstance(data, dict):
                for k, v in list(data.items())[:15]:
                    if isinstance(v, (str, int, float, bool)):
                        results.append({"key": f"{prefix}{str(k).upper().replace(' ', '_')}", "value": str(v)})
                    elif isinstance(v, list) and v and isinstance(v[0], (str, int, float)):
                        results.append({"key": f"{prefix}{str(k).upper().replace(' ', '_')}", "value": ", ".join(str(x) for x in v[:5])})
            elif isinstance(data, list):
                results.append({"key": f"{prefix}ITEM_COUNT", "value": str(len(data))})
        except Exception as e:
            results.append({"key": f"{prefix}DATA_ERROR", "value": str(e)})
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
        elif ext == ".pdf":
            registers.extend(cls.reduce_pdf(file_bytes, filename, prefix=pfx, synthesizer=synthesizer, entity_config=entity_config))
        elif ext in (".docx", ".doc"):
            registers.extend(cls.reduce_docx(file_bytes, filename, prefix=pfx, synthesizer=synthesizer, entity_config=entity_config))
        elif ext in (".json", ".yaml", ".yml"):
            registers.extend(cls.reduce_json_yaml(file_bytes, filename, prefix=pfx))
        elif ext in (".txt", ".md", ".markdown", ".rst", ".log", ".py", ".js", ".html", ".css"):
            registers.extend(cls.reduce_text(file_bytes, filename, prefix=pfx, synthesizer=synthesizer, entity_config=entity_config))
        else:
            # Fallback for arbitrary text-readable files
            try:
                registers.extend(cls.reduce_text(file_bytes, filename, prefix=pfx, synthesizer=synthesizer, entity_config=entity_config))
            except Exception:
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
