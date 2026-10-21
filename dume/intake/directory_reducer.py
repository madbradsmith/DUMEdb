import os
import time
import fnmatch
from pathlib import Path
from typing import Dict, Any, List, Optional, Set

from dume.intake.file_reducer import FileReducer


DEFAULT_IGNORE_PATTERNS = [
    ".git",
    ".git/*",
    "node_modules",
    "node_modules/*",
    "__pycache__",
    "__pycache__/*",
    ".venv",
    ".venv/*",
    "venv",
    "venv/*",
    ".idea",
    ".vscode",
    "dist",
    "dist/*",
    "build",
    "build/*",
    ".dume",
    ".dume/*",
    ".pytest_cache",
    ".ruff_cache",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.tmp",
    "*.lock",
    "package-lock.json"
]


class DirectoryReducer:
    """
    Deterministic Directory Reducer & Crawler for DUMEdb.
    Recursively scans directory trees, applies intelligent filtering,
    hashes files for content-addressable deduplication, and digests
    all assets into atomic LMDB register sets with zero prompt bloat.
    """

    @staticmethod
    def is_ignored(rel_path: str, name: str, ignore_patterns: List[str]) -> bool:
        """Determines if a file or directory matches any ignore pattern."""
        rel_norm = rel_path.replace("\\", "/").strip("/")
        parts = rel_norm.split("/")
        
        for pat in ignore_patterns:
            pat_clean = pat.rstrip("/*")
            # Check directory components directly
            if any(p == pat_clean for p in parts):
                return True
            # Check glob match against relative path and basename
            if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(rel_norm, pat):
                return True
        return False

    @classmethod
    def crawl_directory(
        cls,
        directory_path: str,
        recursive: bool = True,
        max_depth: int = 12,
        max_files: int = 2000,
        max_file_size_bytes: int = 25 * 1024 * 1024,
        ignore_patterns: Optional[List[str]] = None
    ) -> List[Path]:
        """
        Walks directory tree and gathers all candidate file paths.
        Enforces depth limits, ignore patterns, and size boundaries.
        """
        root = Path(directory_path).resolve()
        if not root.exists() or not root.is_dir():
            raise FileNotFoundError(f"Directory not found or not a valid directory: {directory_path}")

        patterns = list(DEFAULT_IGNORE_PATTERNS)
        if ignore_patterns:
            patterns.extend(ignore_patterns)

        discovered_files: List[Path] = []
        root_depth = len(root.parts)

        for current_root, dirs, files in os.walk(root):
            curr_path = Path(current_root)
            depth = len(curr_path.parts) - root_depth
            if not recursive and depth > 0:
                dirs.clear()
                continue
            if depth > max_depth:
                dirs.clear()
                continue

            # Prune ignored directories in-place
            dirs[:] = [
                d for d in dirs
                if not cls.is_ignored(str((curr_path / d).relative_to(root)), d, patterns)
            ]

            for f in sorted(files):
                if len(discovered_files) >= max_files:
                    break
                file_path = curr_path / f
                rel_path = str(file_path.relative_to(root))
                if cls.is_ignored(rel_path, f, patterns):
                    continue

                try:
                    if file_path.stat().st_size <= max_file_size_bytes:
                        discovered_files.append(file_path)
                except (OSError, PermissionError):
                    continue

            if len(discovered_files) >= max_files:
                break

        return discovered_files

    @classmethod
    def reduce_directory(
        cls,
        directory_path: str,
        entity_id: Optional[str] = None,
        recursive: bool = True,
        max_files: int = 2000,
        max_file_size_bytes: int = 25 * 1024 * 1024,
        ignore_patterns: Optional[List[str]] = None,
        prefix_with_relpath: bool = False
    ) -> Dict[str, Any]:
        """
        Recursively digests an entire directory into deterministic register candidates.
        Performs content-hash deduplication and emits clean receipt metrics.
        """
        t0 = time.perf_counter()
        root = Path(directory_path).resolve()
        candidate_paths = cls.crawl_directory(
            directory_path=str(root),
            recursive=recursive,
            max_files=max_files,
            max_file_size_bytes=max_file_size_bytes,
            ignore_patterns=ignore_patterns
        )

        all_registers: List[Dict[str, str]] = []
        seen_keys: Set[str] = set()
        seen_asset_hashes: Set[str] = set()

        files_ingested = 0
        files_skipped_duplicate = 0
        total_bytes = 0

        # Root directory overview registers
        clean_dir_name = root.name.upper().replace(" ", "_")[:12] or "ROOT"
        dir_pfx = f"DIR_{clean_dir_name}"[:24] if not prefix_with_relpath else "DIR"
        
        all_registers.append({"key": f"{dir_pfx}_PATH"[:32], "value": str(root)})
        all_registers.append({"key": f"{dir_pfx}_FILES"[:32], "value": str(len(candidate_paths))})

        for fpath in candidate_paths:
            try:
                rel_path = fpath.relative_to(root).as_posix()
                file_bytes = fpath.read_bytes()
                total_bytes += len(file_bytes)

                # Generate clean prefix per file to prevent collisions
                file_pfx = ""
                if prefix_with_relpath:
                    clean_rel = rel_path.upper().replace("/", "_").replace(".", "_").replace("-", "_")
                    file_pfx = f"F_{clean_rel[:24]}"

                reduction = FileReducer.reduce_file(
                    file_bytes=file_bytes,
                    filename=fpath.name,
                    prefix=file_pfx
                )

                asset_hash = reduction.get("asset_hash", "")
                if asset_hash in seen_asset_hashes:
                    files_skipped_duplicate += 1
                    continue
                seen_asset_hashes.add(asset_hash)

                # Add explicit relative path register
                reg_prefix = f"{file_pfx}_" if file_pfx else ""
                clean_stem = fpath.stem.upper().replace(" ", "_")[:16]
                path_key = f"{reg_prefix}PATH_{clean_stem}"[:32]
                all_registers.append({
                    "key": path_key,
                    "value": rel_path
                })

                for reg in reduction.get("registers", []):
                    k = reg["key"][:32]
                    v = reg["value"]
                    if k not in seen_keys:
                        seen_keys.add(k)
                        all_registers.append({"key": k, "value": v})

                files_ingested += 1

            except Exception:
                continue

        duration_ms = round((time.perf_counter() - t0) * 1000, 2)

        return {
            "directory_path": str(root),
            "directory_name": root.name,
            "entity_id": entity_id or f"DIR-{root.name}",
            "files_scanned": len(candidate_paths),
            "files_ingested": files_ingested,
            "files_skipped_duplicate": files_skipped_duplicate,
            "total_bytes_processed": total_bytes,
            "duration_ms": duration_ms,
            "total_registers_extracted": len(all_registers),
            "registers": all_registers
        }

    @classmethod
    def ingest_directory_to_lmdb(
        cls,
        directory_path: str,
        entity_id: str,
        batch_engine: Any,
        recursive: bool = True,
        max_files: int = 2000,
        ignore_patterns: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Crawls directory and commits distilled registers directly into LMDB
        using the atomic BatchIngestionEngine.
        """
        reduction = cls.reduce_directory(
            directory_path=directory_path,
            entity_id=entity_id,
            recursive=recursive,
            max_files=max_files,
            ignore_patterns=ignore_patterns
        )

        import uuid
        target_entity = entity_id or reduction["entity_id"]
        try:
            uuid.UUID(target_entity)
            canonical_uuid = target_entity
        except ValueError:
            canonical_uuid = str(uuid.uuid5(uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8"), target_entity))

        reg_dict = {r["key"]: r["value"] for r in reduction["registers"] if isinstance(r, dict) and "key" in r}

        commit_result = batch_engine.process_batch(
            entity_id=canonical_uuid,
            registers=reg_dict,
            flush_scratchpad=False
        )

        return {
            **reduction,
            "commit_status": commit_result.get("status", "success"),
            "committed_registers_count": commit_result.get("committed_count", 0),
            "auto_minted_opcodes": commit_result.get("auto_minted_opcodes", 0)
        }


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser(description="DUMEdb Directory Ingestion Engine")
    parser.add_argument("--path", "-p", required=True, help="Path to directory to ingest")
    parser.add_argument("--entity", "-e", default=None, help="Target entity ID in DUMEdb")
    parser.add_argument("--max-files", type=int, default=1000, help="Max files to process")
    parser.add_argument("--json", action="store_true", help="Output raw JSON summary")
    args = parser.parse_args()

    result = DirectoryReducer.reduce_directory(
        directory_path=args.path,
        entity_id=args.entity,
        max_files=args.max_files
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n⚡ DUMEdb Directory Ingest Summary for: {result['directory_path']}")
        print(f"📁 Files Scanned: {result['files_scanned']} | Ingested: {result['files_ingested']} | Duplicates Skipped: {result['files_skipped_duplicate']}")
        print(f"⏱️  Duration: {result['duration_ms']} ms | Total Bytes: {round(result['total_bytes_processed'] / 1024, 1)} KB")
        print(f"📊 Registers Extracted: {result['total_registers_extracted']}")
        print("\nTop 10 Registers:")
        for reg in result["registers"][:10]:
            print(f"  • {reg['key']} = {reg['value']}")


if __name__ == "__main__":
    main()
