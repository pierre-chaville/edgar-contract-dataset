#!/usr/bin/env python3
"""
Normalize contract types across scopes.

Reads mapping from a mapping file (default: mapping.json if present else normalize.json).
Combines all `dataset/filings_[scope].json` into a single `dataset/filings.json`,
keeping only entries that have metadata and a non-null normalized contract type.

Normalization rule:
- Prefer lookup by metadata.contract_category → mapping section (case-insensitive). If the
  category is missing or unknown, fall back to searching the 'other' section and then any
  section for a matching contract_type.
- Within the chosen section(s), map metadata.contract_type to a normalized string.
- Matching is case-insensitive; first exact or case-insensitive key match wins.

Output:
- Writes combined list to `dataset/filings.json`
- For kept entries, updates `metadata.contract_type` to normalized value and also adds
  `metadata.contract_type_normalized` with the same value for clarity. Adds `scope` field if not present.
- Removes `metadata.contract_category` in the output (no longer used downstream).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from typing import Any, Dict, List, Optional


def configure_logging(level: str) -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def detect_mapping_file(mapping_file_arg: Optional[str]) -> str:
    if mapping_file_arg:
        return mapping_file_arg
    # Prefer mapping.json if present, else normalize.json
    if os.path.exists("mapping.json"):
        return "mapping.json"
    return "normalize.json"


def normalize_contract_type(
    mapping: Dict[str, Dict[str, Optional[str]]],
    contract_category: Optional[str],
    contract_type: Optional[str],
) -> Optional[str]:
    # Require a candidate type; category is optional
    if not contract_type:
        return None

    type_value = str(contract_type).strip()
    lower_value = type_value.lower()

    # If a category is provided, attempt within that section first
    category_key = str(contract_category).strip().lower() if contract_category else None
    if category_key:
        section = mapping.get(category_key) or mapping.get("other", {})
        # 1) Direct exact match
        if type_value in section:
            return section[type_value]
        # 2) Case-insensitive match
        for k, v in section.items():
            if k.lower() == lower_value:
                return v
        # 3) Try explicit 'other' section if not already used
        if category_key != "other" and "other" in mapping:
            other_section = mapping["other"]
            if type_value in other_section:
                return other_section[type_value]
            for k, v in other_section.items():
                if k.lower() == lower_value:
                    return v

    # If no category or not found above, search 'other' then any section
    if "other" in mapping:
        other_section2 = mapping["other"]
        if type_value in other_section2:
            return other_section2[type_value]
        for k, v in other_section2.items():
            if k.lower() == lower_value:
                return v

    # Cross-section search as a last resort
    for section_name, section in mapping.items():
        if section_name == "other":
            continue
        if type_value in section:
            return section[type_value]
        for k, v in section.items():
            if k.lower() == lower_value:
                return v

    return None


def process(dataset_dir: str, mapping_file: Optional[str], output_path: Optional[str]) -> None:
    mapping_path = detect_mapping_file(mapping_file)
    if not os.path.exists(mapping_path):
        raise FileNotFoundError(f"Mapping file not found: {mapping_path}")
    mapping = read_json(mapping_path)
    if not isinstance(mapping, dict):
        raise ValueError("Mapping file must contain a JSON object: { 'category': { 'type': 'normalized' } }")

    combined: List[Dict[str, Any]] = []

    if not os.path.isdir(dataset_dir):
        raise FileNotFoundError(f"Dataset directory not found: {dataset_dir}")

    for name in sorted(os.listdir(dataset_dir)):
        if not (name.startswith("filings_") and name.endswith(".json")):
            continue
        scope = name[len("filings_") : -len(".json")]
        filings_path = os.path.join(dataset_dir, name)
        try:
            filings = read_json(filings_path)
        except Exception as exc:
            logging.warning("Failed to read %s: %s", filings_path, exc)
            continue
        if not isinstance(filings, list):
            logging.warning("%s is not a list; skipping", filings_path)
            continue

        kept_count = 0
        for record in filings:
            meta = record.get("metadata") if isinstance(record, dict) else None
            if not isinstance(meta, dict):
                continue
            cat = meta.get("contract_category")
            typ = meta.get("contract_type")
            normalized = normalize_contract_type(mapping, cat, typ)
            if normalized is None:
                continue
            # Update record for output
            record = dict(record)
            meta_out = dict(meta)
            meta_out["contract_type_normalized"] = normalized
            meta_out["contract_type"] = normalized
            # Drop contract_category from output metadata (no longer used)
            meta_out.pop("contract_category", None)
            record["metadata"] = meta_out
            record.setdefault("scope", scope)
            combined.append(record)
            kept_count += 1
        logging.info("%s: kept %s/%s after normalization", scope, kept_count, len(filings))

    out_path = output_path or os.path.join(dataset_dir, "filings.json")
    write_json(out_path, combined)
    logging.info("Wrote %s normalized filings to %s", len(combined), out_path)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Normalize contract types and combine filings")
    p.add_argument("--dataset-dir", default="dataset", help="Dataset directory")
    p.add_argument(
        "--mapping-file",
        default=None,
        help="Mapping file path (defaults to mapping.json if exists, else normalize.json)",
    )
    p.add_argument("--output", default=None, help="Output file path (default: dataset/filings.json)")
    p.add_argument("--log-level", default="INFO", help="Logging level")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)
    process(dataset_dir=args.dataset_dir, mapping_file=args.mapping_file, output_path=args.output)


if __name__ == "__main__":
    main()



