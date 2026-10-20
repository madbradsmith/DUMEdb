import os
import pytest
from pathlib import Path
from dume.intake.file_reducer import FileReducer, save_asset, ASSETS_DIR
from dume.storage.lmdb_engine import DUMEMemoryEngine
from dume.schema.dictionary import SchemaDictionary
from dume.core.record import generate_uuidv7_bytes


def test_asset_saving_and_hashing():
    sample_content = b"Date,Category,Amount\n2026-09-04,Production,5000\n"
    asset_hash, asset_path = save_asset(sample_content, "q3_budget.csv")

    assert len(asset_hash) == 64
    assert Path(asset_path).exists()
    assert Path(asset_path).name == f"{asset_hash}.csv"


def test_file_intake_csv_reducer():
    csv_content = b"Date,Category,Amount,Vendor\n2026-09-04,Equipment,12500,ARRI\n2026-09-05,Catering,1500,Crafty\n"
    res = FileReducer.reduce_file(csv_content, "Q3_Production_Budget.csv", prefix="DOC_")

    assert res["filename"] == "Q3_Production_Budget.csv"
    assert len(res["asset_hash"]) == 64
    assert "DOC_ASSET_HASH" in [r["key"] for r in res["registers"]]
    assert "DOC_ASSET_PATH" in [r["key"] for r in res["registers"]]

    reg_map = {r["key"]: r["value"] for r in res["registers"]}
    assert reg_map.get("DOC_ROW_COUNT") == "2"
    assert "Date,Category,Amount,Vendor" in reg_map.get("DOC_COLUMNS", "")
    assert reg_map.get("DOC_SAMPLE_DATE") == "2026-09-04"
    assert reg_map.get("DOC_SAMPLE_CATEGORY") == "Equipment"


def test_file_intake_xlsx_reducer():
    xlsx_bytes = b"PK\x03\x04DummyZipForXlsxTest"
    res = FileReducer.reduce_file(xlsx_bytes, "Project_Schedule.xlsx", prefix="SCHED_")

    assert res["filename"] == "Project_Schedule.xlsx"
    reg_keys = [r["key"] for r in res["registers"]]
    assert "SCHED_ASSET_HASH" in reg_keys
    assert "SCHED_ASSET_PATH" in reg_keys
    assert "SCHED_FILE_NAME" in reg_keys
