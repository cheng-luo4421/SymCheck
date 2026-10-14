"""Check captain's direct_answers.json; never assign scores from raw text."""
import argparse
import json
from pathlib import Path
from problems import SYMBENCH15


def inspect(path):
    records = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(records, list):
        raise ValueError("Expected a JSON list of 15 records")
    by_id = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Each record must be a JSON object")
        key = record.get("id")
        if not isinstance(key, str) or key in by_id:
            raise ValueError("Missing or duplicate problem id")
        if not isinstance(record.get("model_answer"), str) or not record["model_answer"].strip():
            raise ValueError(f"Missing model_answer: {key}")
        by_id[key] = record
    expected_ids = {p["id"] for p in SYMBENCH15}
    if set(by_id) != expected_ids:
        raise ValueError(f"ID mismatch: missing={sorted(expected_ids-set(by_id))}, extra={sorted(set(by_id)-expected_ids)}")
    for problem in SYMBENCH15:
        record = by_id[problem["id"]]
        if record.get("category") != problem["category"]:
            raise ValueError(f"Category mismatch: {problem['id']}")
        if record.get("statement") != problem["statement"]:
            raise ValueError(f"Statement differs; confirm identical benchmark: {problem['id']}")
    return by_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Captain's batch_out/direct_answers.json")
    args = parser.parse_args()
    records = inspect(args.input)
    print(f"PASS: {len(records)} unique IDs; categories, statements and raw answers present")
    print("Scores pending: raw model answers need mathematical equivalence grading.")
