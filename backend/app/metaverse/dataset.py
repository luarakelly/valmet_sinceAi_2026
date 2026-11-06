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

import os
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ask_your_factory_dataset")


def find_data_dir() -> Path:
    """Dynamically resolves the data directory containing the Excel file or cache."""
    candidates = [
        Path(__file__).resolve().parent.parent.parent.parent / "data",
        Path(__file__).resolve().parent.parent.parent / "data",
        Path.cwd() / "data",
        Path("/home/veiston/Documents/github/valmet_sinceAi_2026/data"),
    ]
    for c in candidates:
        if (c / "valmet_builder_pack.xlsx").exists() or (c / "metaverse_cache.json").exists():
            return c
    return candidates[0]


DATA_DIR = find_data_dir()
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

    def get_asset(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Finds an asset by asset_id (e.g. ASSET-017) or tag (e.g. P-005), case-insensitively."""
        clean = identifier.strip().lower()
        for a in self.get_assets():
            if str(a.get("asset_id", "")).strip().lower() == clean or str(a.get("tag", "")).strip().lower() == clean:
                return a
        return None

    def get_scene_anchors(self, normalized: bool = False) -> List[Dict[str, Any]]:
        """Returns spatial anchor definitions, optionally normalized to Three.js 3D boiler room space."""
        anchors = self.data.get("Scene_Anchors", [])
        states = {s["asset_id"]: s for s in self.data.get("Current_State", []) if "asset_id" in s}

        result = []
        for a in anchors:
            item = dict(a)
            aid = a.get("asset_id")
            if aid in states:
                st = states[aid]
                item["health_score"] = st.get("health_score")
                item["condition_state"] = st.get("condition_state")
                item["issue_code"] = st.get("issue_code")

            if normalized:
                raw_x = float(item.get("x_local_m", 0.0))
                raw_y = float(item.get("y_local_m", 0.0))
                raw_z = float(item.get("z_local_m", 0.0))

                u = (raw_x - (-0.32)) / (30.39 - (-0.32) + 1e-6)
                v = (raw_y - (-0.39)) / (15.49 - (-0.39) + 1e-6)
                w = (raw_z - 0.47) / (2.15 - 0.47 + 1e-6)

                item["x_3d"] = round(-5.0 + u * 10.0, 3)
                item["y_3d"] = round(-1.5 + w * 2.0, 3)  # Y is up in Three.js
                item["z_3d"] = round(-5.0 + v * 5.5, 3)  # Z is depth in Three.js

            result.append(item)
        return result

    def get_telemetry(self, identifier: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Returns chronological telemetry samples for an asset."""
        clean = identifier.strip().lower()
        telemetry = self.data.get("Telemetry_Sample_3d", [])
        records = [
            r for r in telemetry
            if str(r.get("asset_id", "")).strip().lower() == clean
            or str(r.get("tag", "")).strip().lower() == clean
        ]
        if limit > 0:
            return records[-limit:]
        return records

    def get_events(self, identifier: Optional[str] = None, limit: int = 50, severity: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns recent alarms and events."""
        events = self.data.get("Alarms_Events", [])
        if identifier:
            clean = identifier.strip().lower()
            events = [
                e for e in events
                if str(e.get("asset_id", "")).strip().lower() == clean
                or str(e.get("tag", "")).strip().lower() == clean
            ]
        if severity:
            events = [e for e in events if str(e.get("severity", "")).lower() == severity.strip().lower()]
        if limit > 0:
            return events[:limit]
        return events

    def get_work_orders(self, identifier: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """Returns past maintenance work orders."""
        wos = self.data.get("Maintenance_History", [])
        if identifier:
            clean = identifier.strip().lower()
            wos = [
                w for w in wos
                if str(w.get("asset_id", "")).strip().lower() == clean
                or str(w.get("tag", "")).strip().lower() == clean
            ]
        if limit > 0:
            return wos[:limit]
        return wos

    def get_documents(self) -> List[Dict[str, Any]]:
        """Returns knowledge documents."""
        return self.data.get("Knowledge_Docs", [])

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Finds knowledge document by doc_id."""
        clean = doc_id.strip().lower()
        for d in self.get_documents():
            if str(d.get("doc_id", "")).strip().lower() == clean:
                return d
        return None

    def get_data_quality(self, identifier: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns data quality anomalies for an asset."""
        dqs = self.data.get("Data_Quality", [])
        if identifier:
            clean = identifier.strip().lower()
            dqs = [
                q for q in dqs
                if str(q.get("asset_id", "")).strip().lower() == clean
                or str(q.get("tag", "")).strip().lower() == clean
            ]
        return dqs

    def get_historical_cases(self, asset_class: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns historical reference service cases."""
        cases = self.data.get("Historical_Service_Cases", [])
        if asset_class:
            clean = asset_class.strip().lower()
            cases = [c for c in cases if str(c.get("asset_class", "")).strip().lower() == clean]
        return cases

    def get_rag_corpus(self, identifier: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns markdown corpus indices."""
        corpus = self.data.get("RAG_Corpus_Index", [])
        if identifier:
            clean = identifier.strip().lower()
            corpus = [
                c for c in corpus
                if str(c.get("asset_id", "")).strip().lower() == clean
                or str(c.get("tag", "")).strip().lower() == clean
            ]
        return corpus

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Calculates aggregated plant-level KPIs from Current_State and Alarms."""
        states = self.data.get("Current_State", [])
        events = self.data.get("Alarms_Events", [])

        total_assets = len(states)
        if total_assets == 0:
            return {"total_assets": 0}

        health_scores = [float(s.get("health_score", 100)) for s in states]
        avg_health = round(sum(health_scores) / total_assets, 1)

        condition_counts: Dict[str, int] = {}
        for s in states:
            c = s.get("condition_state", "unknown")
            condition_counts[c] = condition_counts.get(c, 0) + 1

        active_alarms = sum(1 for e in events if e.get("status") in ("open", "acknowledged"))
        high_severity_alarms = sum(1 for e in events if e.get("severity") == "high")

        return {
            "total_assets": total_assets,
            "average_health_score": avg_health,
            "condition_distribution": condition_counts,
            "healthy_assets": condition_counts.get("healthy", 0),
            "watch_assets": condition_counts.get("watch", 0),
            "degraded_assets": condition_counts.get("degraded", 0),
            "attention_required_assets": condition_counts.get("attention_required", 0),
            "active_alarms": active_alarms,
            "high_severity_alarms": high_severity_alarms,
        }


_dataset_instance: Optional[MetaverseDataset] = None


def get_dataset() -> MetaverseDataset:
    global _dataset_instance
    if _dataset_instance is None:
        _dataset_instance = MetaverseDataset()
    return _dataset_instance
