from app import list_scopes_flat, flatten_filing


def test_list_scopes_flat_handles_missing_dir(tmp_path):
    assert list_scopes_flat(str(tmp_path / "nope")) == []


def test_list_scopes_flat_finds_scopes(tmp_path):
    d = tmp_path / "dataset"
    d.mkdir()
    (d / "filings_A.json").write_text("[]")
    (d / "filings_B.json").write_text("[]")
    (d / "other.txt").write_text("x")
    assert list_scopes_flat(str(d)) == ["A", "B"]


def test_flatten_filing_builds_expected_fields(tmp_path):
    files_dir = tmp_path / "files"
    files_dir.mkdir(parents=True)
    uid = "abc"
    html_path = files_dir / f"{uid}.htm"
    html_path.write_text("<html></html>")

    filing = {
        "uid": uid,
        "formType": "8-K",
        "metadata": {
            "contract_type": "ISDA",
            "version_type": "2002",
            "contract_date": "2020-01-01",
            "is_amendment": False,
            "amendment_date": None,
            "amendment_number": None,
            "party_1": {"name": "A"},
            "party_2": {"name": "B"},
            "confidence": 0.9,
        },
        "_doc_stats": {"doc_pages_estimate": 3.2},
    }
    row = flatten_filing("SCOPE", filing, str(tmp_path))
    assert row["scope"] == "SCOPE"
    assert row["uid"] == uid
    assert row["formType"] == "8-K"
    assert row["contract_type"] == "ISDA"
    assert row["doc_pages_estimate"] == int(3.2)
    assert str(uid) in str(row["html_path"])  # path chosen


