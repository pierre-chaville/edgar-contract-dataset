import json
import os
from tempfile import TemporaryDirectory

from normalize import normalize_contract_type, process


def test_normalize_contract_type_with_category_exact():
    mapping = {"master": {"ISDA": "ISDA Master Agreement"}}
    assert (
        normalize_contract_type(mapping, contract_category="master", contract_type="ISDA")
        == "ISDA Master Agreement"
    )


def test_normalize_contract_type_case_insensitive_and_fallback():
    mapping = {
        "master": {"ISDA Master Agreement": "ISDA Master Agreement"},
        "other": {"gmra": "Global Master Repurchase Agreement"},
    }
    assert (
        normalize_contract_type(mapping, contract_category="other", contract_type="GMRA")
        == "Global Master Repurchase Agreement"
    )
    # Unknown in category, but exists in other section via case-insensitive key
    assert (
        normalize_contract_type(mapping, contract_category="master", contract_type="gmra")
        == "Global Master Repurchase Agreement"
    )


def test_process_combines_and_filters_records(tmp_path):
    dataset_dir = tmp_path / "dataset"
    os.makedirs(dataset_dir, exist_ok=True)
    # Create two scope files
    filings_isda = [
        {"uid": "1", "metadata": {"contract_category": "master", "contract_type": "ISDA"}},
        {"uid": "2", "metadata": {"contract_category": "master", "contract_type": "Unknown"}},
        {"uid": "3", "metadata": None},
    ]
    filings_gmra = [
        {"uid": "4", "metadata": {"contract_category": "master", "contract_type": "GMRA"}},
    ]
    (dataset_dir / "filings_ISDA.json").write_text(json.dumps(filings_isda))
    (dataset_dir / "filings_GMRA.json").write_text(json.dumps(filings_gmra))

    mapping = {
        "master": {
            "ISDA": "ISDA Master Agreement",
            "GMRA": "Global Master Repurchase Agreement",
        },
        "other": {"other": None},
    }
    mapping_path = tmp_path / "normalize.json"
    mapping_path.write_text(json.dumps(mapping))

    out_path = tmp_path / "out.json"
    process(dataset_dir=str(dataset_dir), mapping_file=str(mapping_path), output_path=str(out_path))

    data = json.loads(out_path.read_text())
    # Record uid=2 should be filtered out due to Unknown mapping
    uids = sorted([r["uid"] for r in data])
    assert uids == ["1", "4"]
    # Check normalized fields and scope presence
    rec1 = next(r for r in data if r["uid"] == "1")
    assert rec1["metadata"]["contract_type"] == "ISDA Master Agreement"
    assert rec1["metadata"]["contract_type_normalized"] == "ISDA Master Agreement"
    assert rec1["scope"] == "ISDA"


