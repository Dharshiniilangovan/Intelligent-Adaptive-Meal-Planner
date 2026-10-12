"""Fast, read-only UI preview from a previously saved E2E run."""
import json
from pathlib import Path

REPORT = Path(__file__).resolve().parents[2] / 'reports' / 'day5_e2e_output.json'


def load_demo_plan() -> dict:
    if not REPORT.is_file():
        raise FileNotFoundError(f'No saved E2E result at {REPORT}')
    with REPORT.open(encoding='utf-8') as handle:
        result = json.load(handle)
    if not isinstance(result, dict) or not isinstance(result.get('plan'), dict):
        raise ValueError('Saved E2E file is not a valid planner result.')
    if not isinstance(result.get('grocery_basket'), dict):
        raise ValueError('Saved E2E file has no grocery basket.')
    return result
