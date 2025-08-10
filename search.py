import argparse
import logging
import time
from typing import Any, Dict, List, Sequence
import uuid
import os
import json
import re
import html as html_module
from sec_api import FullTextSearchApi, RenderApi


def configure_logging(level: str) -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass


def get_api_key() -> str:
    api_key = os.getenv("SEC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Environment variable SEC_API_KEY is not set. Set it in your shell or in a .env file."
        )
    return api_key


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def html_contains_keywords(html_content: str, keywords: Sequence[str]) -> bool:
    if not keywords:
        return True
    if not html_content:
        return False
    cleaned = re.sub(r"(?is)<(script|style).*?>.*?</\\1>", " ", html_content)
    cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
    cleaned = html_module.unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    head = cleaned[:500]
    for kw in keywords:
        if not kw:
            continue
        if kw.lower() not in head:
            return False
    return True

def load_scopes(scope_file: str) -> List[Dict[str, Any]]:
    with open(scope_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("scope.json must contain a list of scope objects")
    return data


def normalize_query(search_field: Any) -> str:
    if isinstance(search_field, list):
        return search_field[0] if search_field else ""
    return str(search_field or "")


def fetch_filings_for_year(
    api: FullTextSearchApi,
    query: str,
    year: int,
    forms: Sequence[str],
) -> Dict[str, Any]:
    params = {
        "query": query,
        "formTypes": list(forms),
        "startDate": f"{year}-01-01",
        "endDate": f"{year}-12-31",
    }
    logging.debug("search_parameters=%s", params)
    return api.get_filings(params)


def save_scope_filings_json(base_dir: str, scope_type: str, filings: List[Dict[str, Any]]) -> str:
    target_dir = os.path.join(base_dir, scope_type)
    ensure_dir(target_dir)
    out_path = os.path.join(target_dir, "filings.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(filings, f, indent=2)
    return out_path


def download_and_filter_filings(
    renderer: RenderApi,
    base_dir: str,
    scope_type: str,
    filings: Sequence[Dict[str, Any]],
    keywords: Sequence[str],
    delay_ms: int,
) -> List[Dict[str, Any]]:
    # Save filtered files directly under dataset/<scope_type>
    files_dir = os.path.join(base_dir, scope_type)
    ensure_dir(files_dir)
    selected: List[Dict[str, Any]] = []
    for filing in filings:
        filing_url = filing.get("filingUrl")
        accession_no = filing.get("accessionNo")
        if not filing_url or not filing_url.endswith(".htm") or not accession_no:
            continue
        uid = uuid.uuid5(uuid.NAMESPACE_URL, f"{accession_no}|{filing_url}").hex
        out_path = os.path.join(files_dir, f"{uid}.htm")
        if os.path.exists(out_path):
            logging.debug("Skip existing %s", out_path)
            record = dict(filing)
            record["uid"] = uid
            selected.append(record)
            continue
        try:
            html_str = renderer.get_filing(url=filing_url)
        except Exception as exc:
            logging.warning("Failed to download %s: %s", filing_url, exc)
            continue
        if not html_contains_keywords(html_str, keywords):
            continue
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html_str)
        logging.info("Saved %s", out_path)
        record = dict(filing)
        record["uid"] = uid
        selected.append(record)
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)
    return selected


def process_scopes(
    scope_file: str,
    output_dir: str,
    forms: Sequence[str],
    delay_ms: int,
) -> None:
    load_env()
    api_key = get_api_key()
    search_api = FullTextSearchApi(api_key)
    render_api = RenderApi(api_key)

    scopes = load_scopes(scope_file)
    for scope in scopes:
        scope_type = str(scope.get("type", "unknown"))
        query = normalize_query(scope.get("search", ""))
        start_year = int(scope.get("start", 0))
        end_year = int(scope.get("end", start_year))
        logging.info("Processing scope=%s years=%s-%s", scope_type, start_year, end_year)
        scope_selected: List[Dict[str, Any]] = []
        for year in range(start_year, end_year + 1):
            try:
                response = fetch_filings_for_year(search_api, query, year, forms)
            except Exception as exc:
                logging.error("Search failed for %s %s: %s", scope_type, year, exc)
                continue
            filings = response.get("filings", [])
            total_value = response.get("total", {}).get("value", len(filings))
            logging.info("%s %s: total=%s", scope_type, year, total_value)
            selected = download_and_filter_filings(
                render_api,
                output_dir,
                scope_type,
                filings,
                scope.get("keywords", []),
                delay_ms,
            )
            scope_selected.extend(selected)
            logging.info("%s %s: saved=%s", scope_type, year, len(selected))

        # Save only filtered filings metadata per scope
        save_scope_filings_json(output_dir, scope_type, scope_selected)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search and download SEC filings per scope and year.")
    parser.add_argument("--scope-file", default="scope.json", help="Path to scope JSON file")
    parser.add_argument("--output-dir", default="dataset", help="Base output directory")
    parser.add_argument(
        "--forms",
        nargs="+",
        default=["8-K", "10-Q"],
        help="Form types to include (space-separated)",
    )
    parser.add_argument("--delay-ms", type=int, default=0, help="Delay in ms between downloads")
    parser.add_argument("--log-level", default="INFO", help="Logging level (DEBUG, INFO, WARNING, ERROR)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)
    process_scopes(
        scope_file=args.scope_file,
        output_dir=args.output_dir,
        forms=args.forms,
        delay_ms=args.delay_ms,
    )


if __name__ == "__main__":
    main()






