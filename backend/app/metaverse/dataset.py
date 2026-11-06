"""Ask Your Factory Synthetic Industrial Data Pack Loader & Cache.

Parses all sheets from valmet_builder_pack.xlsx or reads pre-parsed JSON cache:
- Asset_Master (30 assets)
- Scene_Anchors (30 3D spatial anchor records)
- Current_State (health scores, condition states, diagnostic codes)
- Telemetry_Sample_3d (4,320 multivariate timeseries records)
- Alarms_Events (1,000 synthetic alarms and inspection notes)
- Maintenance_History (300 past work orders)
- Historical_Service_Cases (50 past reference cases)
- Knowledge_Docs (8 core engineering, safety, and RAG guidelines)
- Data_Quality (120 data quality issues)
- RAG_Corpus_Index (38 markdown documentation entries)
- API_Contract & Dashboard
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ask_your_factory_dataset")


DATA_DIR = Path(__file__).resolve().parents[3] / "data"
EXCEL_PATH = DATA_DIR / "valmet_builder_pack.xlsx"
CACHE_PATH = DATA_DIR / "metaverse_cache.json"


class MetaverseDataset:
    """In-memory dataset cache and extractor for the Ask Your Factory data pack."""

    def __init__(self, excel_path: Path = EXCEL_PATH, cache_path: Path = CACHE_PATH):
        self.excel_path = excel_path
        self.cache_path = cache_path
        self.data: Dict[str, Any] = {}
        self.load()

    def _parse_excel(self) -> Dict[str, Any]:
        """Parses all sheets directly from Excel via openpyxl."""
        if not self.excel_path.exists():
            logger.warning(f"Excel workbook not found at {self.excel_path}")
            return {}

        try:
            import openpyxl
        except ImportError:
            logger.error("openpyxl is not installed. Please install openpyxl or supply data/metaverse_cache.json.")
            return {}

        logger.info(f"Parsing Excel workbook from {self.excel_path}...")
        wb = openpyxl.load_workbook(str(self.excel_path), data_only=True)
        dataset: Dict[str, Any] = {}

        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            rows = list(sheet.iter_rows(values_only=True))
            if not rows:
                dataset[sheet_name] = []
                continue

            headers = []
            for idx, col in enumerate(rows[0]):
                if col is not None:
                    headers.append(str(col).strip())
                else:
                    headers.append(f"col_{idx}")
            sheet_records: List[Dict[str, Any]] = []

            for row in rows[1:]:
                if all(v is None for v in row):
                    continue
                record = {}
                for h, val in zip(headers, row):
                    if hasattr(val, "isoformat"):
                        record[h] = val.isoformat()
                    else:
                        record[h] = val
                sheet_records.append(record)

            dataset[sheet_name] = sheet_records

        logger.info(f"Parsed {len(dataset)} sheets from Excel.")
        return dataset

    def load(self, force_reload: bool = False) -> None:
        """Loads dataset from JSON cache if present, otherwise parses Excel and writes cache."""
        if not force_reload and self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                if self.data and "Asset_Master" in self.data:
                    return
            except Exception as e:
                logger.warning(f"Failed to load JSON cache: {e}. Falling back to Excel parse.")

        self.data = self._parse_excel()
        if self.data and "Asset_Master" in self.data:
            try:
                with open(self.cache_path, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, indent=2, default=str)
                logger.info(f"Updated JSON cache at {self.cache_path}")
            except Exception as e:
                logger.warning(f"Failed to write cache to {self.cache_path}: {e}")


    def get_assets(self) -> List[Dict[str, Any]]:
        """Returns 30 assets joined with their current state and scene anchor."""
        assets = self.data.get("Asset_Master", [])
        states = {s["asset_id"]: s for s in self.data.get("Current_State", []) if "asset_id" in s}
        anchors = {a["asset_id"]: a for a in self.data.get("Scene_Anchors", []) if "asset_id" in a}

        combined = []
        for asset in assets:
            aid = asset.get("asset_id")
            item = dict(asset)
            if aid in states:
                item["state"] = states[aid]
            if aid in anchors:
                item["anchor"] = anchors[aid]
            combined.append(item)
        return combined


_dataset_instance: Optional[MetaverseDataset] = None


def get_dataset() -> MetaverseDataset:
    global _dataset_instance
    if _dataset_instance is None:
        _dataset_instance = MetaverseDataset()
    return _dataset_instance
