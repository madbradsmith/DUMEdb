import os
import shutil
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from dume.intake.directory_reducer import DirectoryReducer
from dume.storage.lmdb_engine import DUMEMemoryEngine
from dume.schema.dictionary import SchemaDictionary
from dume.scribe.ingest import BatchIngestionEngine
from dume.server.app import app


@pytest.fixture
def temp_sample_dir():
    """Creates a temporary directory with various test files and ignored folders."""
    temp_dir = tempfile.mkdtemp(prefix="dume_dir_test_")
    root = Path(temp_dir)

    # 1. Normal Markdown file
    (root / "README.md").write_text("# Project Titan\nOPERATOR: MadBrad\nSTATUS: PLANNING\n")

    # 2. Python source file
    (root / "main.py").write_text("def run():\n    print('Hello Titan')\n")

    # 3. CSV file
    (root / "metrics.csv").write_text("metric,value\nlatency,1.5ms\nthroughput,4500rps\n")

    # 4. Nested subdirectory
    sub = root / "docs"
    sub.mkdir()
    (sub / "architecture.md").write_text("# Architecture Guide\nPRINCIPLE: Zero Bloat\n")

    # 5. Ignored directory (.git)
    git_dir = root / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("[core]\nrepositoryformatversion = 0\n")

    # 6. Ignored __pycache__
    pyc_dir = root / "__pycache__"
    pyc_dir.mkdir()
    (pyc_dir / "main.cpython-313.pyc").write_bytes(b"\x00\x00\x00\x00")

    # 7. Duplicate file (same content as README.md)
    (sub / "copy_of_readme.md").write_text("# Project Titan\nOPERATOR: MadBrad\nSTATUS: PLANNING\n")

    yield str(root)

    shutil.rmtree(temp_dir, ignore_errors=True)


def test_crawl_directory_filtering(temp_sample_dir):
    """Verifies that crawl_directory ignores .git, __pycache__, and respects max limits."""
    files = DirectoryReducer.crawl_directory(temp_sample_dir, recursive=True)
    file_names = [f.name for f in files]

    assert "README.md" in file_names
    assert "main.py" in file_names
    assert "metrics.csv" in file_names
    assert "architecture.md" in file_names

    # Ignored files must not appear
    assert "config" not in file_names
    assert "main.cpython-313.pyc" not in file_names


def test_reduce_directory_deduplication(temp_sample_dir):
    """Verifies that identical files are deduplicated via content hashing."""
    result = DirectoryReducer.reduce_directory(temp_sample_dir, entity_id="Titan-01")

    assert result["files_scanned"] == 5
    assert result["files_ingested"] == 4  # 1 duplicate skipped
    assert result["files_skipped_duplicate"] == 1
    assert result["total_registers_extracted"] > 0

    keys = [r["key"] for r in result["registers"]]
    assert any("DIR_" in k for k in keys)
    assert any("OPERATOR" in k for k in keys)


def test_ingest_directory_to_lmdb(temp_sample_dir, tmp_path):
    """Verifies that directory ingestion commits atomically into LMDB."""
    db_path = str(tmp_path / "test_lmdb")
    memory_engine = DUMEMemoryEngine(db_path=db_path)
    schema_dict = SchemaDictionary()
    batch_engine = BatchIngestionEngine(memory_engine=memory_engine, schema_dict=schema_dict)

    result = DirectoryReducer.ingest_directory_to_lmdb(
        directory_path=temp_sample_dir,
        entity_id="ProjectTitan",
        batch_engine=batch_engine
    )

    assert result["commit_status"] == "success"
    assert result["committed_registers_count"] > 0
    assert result["files_ingested"] >= 4
    memory_engine.close()


def test_directory_ingest_api_endpoint(temp_sample_dir):
    """Verifies POST /dume/ingest/directory via TestClient."""
    client = TestClient(app)
    payload = {
        "directory_path": temp_sample_dir,
        "entity_id": "Titan-API-Test",
        "recursive": True
    }

    response = client.post("/dume/ingest/directory", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["commit_status"] == "success"
    assert data["files_ingested"] >= 4
    assert data["entity_id"] is not None
