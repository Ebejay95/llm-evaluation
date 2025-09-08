import json
from pathlib import Path
from typing import Dict, Any, List

# Basisordner: resources/knowledge-base
BASE = Path(__file__).resolve().parent.parent / "knowledge-base"

def _load(name: str) -> List[Dict[str, Any]]:
    return json.loads((BASE / name).read_text(encoding="utf-8"))

def load_company(company_id: str) -> Dict[str, Any]:
    companies = _load("company_profiles.json")
    m = next((c for c in companies if c["id"] == company_id), None)
    if not m:
        raise ValueError(f"Company {company_id} not found")
    return m

def load_scenarios() -> List[Dict[str, Any]]:
    return _load("library_scenarios.json")

def load_controls() -> Dict[str, Dict[str, Any]]:
    arr = _load("library_controls.json")
