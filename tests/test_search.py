import sys
import types
import importlib
import pytest

# Provide a minimal stub for sec_api to allow importing search.py without the package
if "sec_api" not in sys.modules:
    sec_api_stub = types.ModuleType("sec_api")
    class FullTextSearchApi:  # noqa: D401 - simple stub
        """Stub"""
        pass
    class RenderApi:  # noqa: D401 - simple stub
        """Stub"""
        pass
    sec_api_stub.FullTextSearchApi = FullTextSearchApi
    sec_api_stub.RenderApi = RenderApi
    sys.modules["sec_api"] = sec_api_stub

search = importlib.import_module("search")
html_contains_keywords = search.html_contains_keywords
normalize_query = search.normalize_query


def test_html_contains_keywords_empty_keywords_true():
    assert html_contains_keywords("<html></html>", []) is True


def test_html_contains_keywords_missing_keyword_false():
    html = "<html><body>hello world</body></html>"
    assert html_contains_keywords(html, ["hello", "missing"]) is False


def test_html_contains_keywords_strips_tags_and_entities():
    html = (
        "<html><head><style>.x{}</style><script>var a=1;</script></head>"
        "<body>&nbsp;ISDA <b>Master</b> Agreement</body></html>"
    )
    assert html_contains_keywords(html, ["isda", "master"]) is True


def test_html_contains_keywords_checks_head_only():
    # Place keyword after the first 500 characters so it shouldn't be found
    long_prefix = ("word " * 200).strip()  # ~1000 characters
    html = f"<body>{long_prefix} TARGET</body>"
    assert html_contains_keywords(html, ["target"]) is False


def test_normalize_query():
    assert normalize_query(["a", "b"]) == "a"
    assert normalize_query("x") == "x"
    assert normalize_query(None) == ""


