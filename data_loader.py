import os
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
REAL_DATA = ROOT / "data" / "raw" / "postings.csv"
SAMPLE_DATA = ROOT / "data" / "sample_postings.csv"

TEXT_COLUMNS = [
    "job_title", "company", "job_location", "job_link", "job_level",
    "job_type", "job_summary", "job_skills",
]

def _split_skills(raw: str) -> list[str]:
    parts = re.split(r"[,;|]", raw.lower())
    return [p.strip() for p in parts if p.strip()]

def resolve_data_path() -> Path:
    override = os.environ.get("SKILLSCOUT_DATA")
    if override:
        return Path(override)
    return REAL_DATA if REAL_DATA.exists() else SAMPLE_DATA

def load_postings(path: Path | None = None) -> pd.DataFrame:
    path = path or resolve_data_path()
    df = pd.read_csv(path, dtype=str)
    for col in TEXT_COLUMNS:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").str.strip()
    df = df[(df["job_title"] != "") & (df["company"] != "")].reset_index(drop=True)
    df["id"] = df.index
    df["skills_list"] = df["job_skills"].apply(_split_skills)
    return df