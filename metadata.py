#!/usr/bin/env python3
"""
Analyze downloaded SEC exhibit HTML files per scope and extract contract metadata using an LLM via LangChain.

Workflow:
- For each scope in `scope.json`, open `dataset/<scope>/filings.json` if present to determine target files.
- For each corresponding HTML file `<uid>.htm` under `dataset/<scope>`, convert HTML to text and take the first ~500-1000 words.
- Prompt an LLM (OpenAI via LangChain) to extract structured metadata:
  - document_type: one of [contract, confirmation, other]
  - contract_category: one of [master, collateral, facility, other]
  - contract_type: e.g., ISDA, GMRA, etc.
  - version_type: e.g., 2002, 92, etc.
  - contract_date: YYYY-MM-DD when determinable
  - is_amendment: boolean
  - amendment_date: YYYY-MM-DD if applicable
  - amendment_number: string/identifier if applicable
  - party_1: { name, address }
  - party_2: { name, address }
  - explanation: brief rationale for choices
  - confidence: float [0.0, 1.0]

Results are written back into each scope's `filings.json` by augmenting each filing object with a `metadata` field.

Requirements:
- OPENAI_API_KEY must be set in environment (or via .env). See README for details.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

# LangChain / OpenAI
try:
    # Core Prompting / Pydantic v1 shim
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.pydantic_v1 import BaseModel, Field
    from langchain_openai import ChatOpenAI
except Exception as exc:  # pragma: no cover - helpful runtime hint
    raise RuntimeError(
        "LangChain and langchain-openai are required. Install with: pip install langchain langchain-openai"
    ) from exc


def load_env() -> None:
    """Load environment variables from .env if available."""
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv()
    except Exception:
        pass


def configure_logging(level: str) -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def read_json_file(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json_file(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def normalize_whitespace(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def html_to_text_first_words(html: str, max_words: int) -> str:
    """Convert HTML to text and return the first ~max_words words.

    - Removes script/style
    - Extracts visible text
    - Collapses whitespace
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    text = normalize_whitespace(text)
    if not text:
        return ""
    words = text.split(" ")
    snippet = " ".join(words[:max_words])
    return snippet


def html_text_stats(html: str, max_words: int) -> tuple[str, int]:
    """Return (snippet, total_word_count) from HTML.

    - snippet: first ~max_words words
    - total_word_count: full text word count for page estimation
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    text = normalize_whitespace(text)
    if not text:
        return "", 0
    words = text.split(" ")
    snippet = " ".join(words[:max_words])
    return snippet, len(words)


def read_snippet_and_word_count(html_path: str, max_words: int) -> tuple[Optional[str], Optional[int]]:
    try:
        with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
            html = f.read()
    except Exception as exc:
        logging.warning("Failed to read %s: %s", html_path, exc)
        return None, None
    snippet, total_words = html_text_stats(html, max_words=max_words)
    return snippet, total_words


def ensure_exists(path: str) -> bool:
    return os.path.exists(path) and os.path.isfile(path)


class Party(BaseModel):
    name: Optional[str] = Field(None, description="Legal name of the party if identifiable")
    address: Optional[str] = Field(
        None, description="Postal address of the party if identifiable (as appears in the document)"
    )


class ContractMetadata(BaseModel):
    document_type: str = Field(
        ..., description="One of: contract, confirmation, other"
    )
    contract_category: str = Field(
        ..., description="One of: master, collateral, facility, other"
    )
    contract_type: Optional[str] = Field(
        None, description="E.g., ISDA, GMRA, GMSLA, CSA, MRA, MSFTA, other"
    )
    version_type: Optional[str] = Field(
        None, description="Version identifier if any, e.g., 2002, 1992, 2011, 2010, etc."
    )
    contract_date: Optional[str] = Field(
        None, description="Contract date in ISO format YYYY-MM-DD if determinable, else null"
    )
    is_amendment: bool = Field(
        ..., description="True if the document is an amendment/confirmation/variation; False otherwise"
    )
    amendment_date: Optional[str] = Field(
        None, description="Amendment date in ISO format if applicable"
    )
    amendment_number: Optional[str] = Field(
        None, description="Amendment identifier/number if applicable"
    )
    party_1: Party = Field(..., description="Party 1 details (usually first listed party)")
    party_2: Party = Field(..., description="Party 2 details (usually second listed party)")
    explanation: str = Field(
        ..., description="Brief explanation citing phrases from the snippet that support your choices"
    )
    confidence: float = Field(
        ..., description="Confidence score between 0.0 and 1.0 regarding accuracy of the extracted metadata"
    )


def build_chain(model_name: str, temperature: float) -> Any:
    llm = ChatOpenAI(model=model_name, temperature=temperature)
    # Use LCEL with structured output
    structured_llm = llm.with_structured_output(ContractMetadata)
    system = (
        "You are a senior legal documentation analyst. "
        "Extract the requested metadata from the first ~page of a filing exhibit. "
        "Output must follow the provided schema and be grounded strictly in the text. "
        "If unknown, return null/None. Dates should be in YYYY-MM-DD when possible. "
        "Only infer when strongly supported; otherwise prefer null and lower confidence."
    )
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system),
            (
                "human",
                (
                    "Allowed values:\n"
                    "- document_type: contract | confirmation | other. NB: a contract should be an actual contract, not a letter or a memo referring to a contract.\n"
                    "- contract_category: master | collateral | facility | other\n\n"
                    "Document first-page snippet (truncated):\n"  # Not fenced to avoid token overhead
                    "{snippet}\n\n"
                    "Now extract the metadata."
                ),
            ),
        ]
    )
    return prompt | structured_llm


def extract_metadata_html(
    chain: Any, html_path: str, max_words: int
) -> tuple[Optional[ContractMetadata], Optional[int]]:
    snippet, total_words = read_snippet_and_word_count(html_path, max_words=max_words)
    if snippet is None or total_words is None:
        return None, None
    if total_words < 500:
        # Less than ~1 page: skip LLM per requirement
        logging.info("Skipping LLM for short doc (%s words) at %s", total_words, html_path)
        return None, total_words
    if not snippet or len(snippet) < 50:
        logging.info("Insufficient text after HTML extraction for %s", html_path)
        return None, total_words
    try:
        result: ContractMetadata = chain.invoke({"snippet": snippet})
        return result, total_words
    except Exception as exc:
        logging.warning("LLM extraction failed for %s: %s", html_path, exc)
        return None, total_words


def process_scope(
    dataset_dir: str,
    scope_type: str,
    chain: Any,
    max_words: int,
    overwrite: bool,
    max_files: Optional[int] = None,
) -> None:
    scope_dir = os.path.join(dataset_dir, scope_type)
    if not os.path.isdir(scope_dir):
        logging.info("Skip missing scope directory %s", scope_dir)
        return

    filings_path = os.path.join(scope_dir, "filings.json")
    filings: List[Dict[str, Any]] = []
    if ensure_exists(filings_path):
        filings = read_json_file(filings_path)
        if not isinstance(filings, list):
            logging.warning("Expected list in %s; got %s", filings_path, type(filings))
            filings = []
    else:
        # Build from *.htm files if no filings.json exists
        for name in sorted(os.listdir(scope_dir)):
            if name.lower().endswith((".htm", ".html")):
                uid = os.path.splitext(name)[0]
                filings.append({"uid": uid})

    processed = 0
    for filing in filings:
        uid = str(filing.get("uid")) if filing.get("uid") else None
        if not uid:
            continue
        # Skip if already has metadata and not overwriting
        if not overwrite and isinstance(filing.get("metadata"), dict):
            continue
        html_path = os.path.join(scope_dir, f"{uid}.htm")
        if not ensure_exists(html_path):
            # try .html
            html_path = os.path.join(scope_dir, f"{uid}.html")
        if not ensure_exists(html_path):
            logging.debug("HTML not found for uid=%s in %s", uid, scope_dir)
            continue

        meta, total_words = extract_metadata_html(chain, html_path, max_words=max_words)
        # Always record stats
        filing.setdefault("_doc_stats", {})
        if total_words is not None:
            filing["_doc_stats"]["doc_word_count"] = int(total_words)
            filing["_doc_stats"]["doc_pages_estimate"] = float(total_words) / 500.0
        # If short doc, don't call LLM (already skipped inside extractor)
        if meta is None:
            # persist stats even when skipping LLM
            write_json_file(filings_path, filings)
            continue

        # Persist back into object
        filing["metadata"] = meta.dict()
        filing.setdefault("_meta_source", {})
        filing["_meta_source"].update(
            {
                "model": getattr(chain, "model", None) or "openai",
                "max_words": max_words,
                "html_file": os.path.basename(html_path),
            }
        )
        processed += 1

        # Periodically flush to disk to avoid losing work
        if processed % 5 == 0:
            write_json_file(filings_path, filings)
            logging.info("Checkpoint saved %s (processed=%s)", filings_path, processed)

        if max_files and processed >= max_files:
            break

    # Final save
    write_json_file(filings_path, filings)
    logging.info(
        "Wrote metadata for %s entries to %s", processed, filings_path
    )


def load_scopes(scope_file: str) -> List[Dict[str, Any]]:
    data = read_json_file(scope_file)
    if not isinstance(data, list):
        raise ValueError("scope.json must contain a list of scope objects")
    return data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract contract metadata from first-page text of exhibit HTMLs using an LLM via LangChain."
        )
    )
    parser.add_argument("--scope-file", default="scope.json", help="Path to scope JSON file")
    parser.add_argument(
        "--dataset-dir", default="dataset", help="Base dataset directory containing scope subfolders"
    )
    parser.add_argument(
        "--model", default="gpt-5-mini", help="OpenAI chat model name (e.g., gpt-4o-mini, gpt-4o)"
    )
    parser.add_argument("--temperature", type=float, default=0.0, help="LLM temperature")
    parser.add_argument(
        "--max-words",
        type=int,
        default=900,
        help="Max words from first page/snippet to include in the prompt (500-1000 recommended)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing metadata entries in filings.json",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Optional limit of files to process per scope (useful for testing)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)
    load_env()

    chain = build_chain(args.model, args.temperature)

    scopes = load_scopes(args.scope_file)
    for scope in scopes:
        scope_type = str(scope.get("type", "unknown"))
        logging.info("Processing scope %s", scope_type)
        process_scope(
            dataset_dir=args.dataset_dir,
            scope_type=scope_type,
            chain=chain,
            max_words=args.max_words,
            overwrite=args.overwrite,
            max_files=args.max_files,
        )


if __name__ == "__main__":
    main()


