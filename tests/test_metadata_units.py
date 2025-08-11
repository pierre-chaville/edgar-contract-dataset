import pytest


def test_html_text_stats_and_normalize_whitespace():
    try:
        from metadata import html_text_stats, normalize_whitespace
    except Exception:
        pytest.skip("LangChain/bs4 may not be installed in minimal env")

    html = """
    <html>
      <head><style>.x{}</style><script>1</script></head>
      <body>
        Hello\n\n  World   !
      </body>
    </html>
    """
    snippet, total = html_text_stats(html, max_words=3)
    assert total >= 3
    assert len(snippet.split()) <= 3
    assert normalize_whitespace(" a\n b \t ") == "a b"


def test_ensure_exists(tmp_path):
    try:
        from metadata import ensure_exists
    except Exception:
        pytest.skip("LangChain/bs4 may not be installed in minimal env")

    p = tmp_path / "x.txt"
    p.write_text("hi")
    assert ensure_exists(str(p)) is True
    assert ensure_exists(str(tmp_path / "missing.txt")) is False


