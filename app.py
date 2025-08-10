#!/usr/bin/env python3
"""
Streamlit app to browse extracted contract metadata.

Features:
- Loads either a combined `dataset/filings.json` (normalized) or all `dataset/filings_<scope>.json` (pre-normalized)
- HTML files are stored under `dataset/files/`
- Provides filters: contract type, is amendment
- Displays filtered documents as a table with key metadata fields
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import pandas as pd
import altair as alt
import streamlit as st
import streamlit.components.v1 as components


def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_scopes_flat(dataset_dir: str) -> List[str]:
    scopes: List[str] = []
    if not os.path.isdir(dataset_dir):
        return scopes
    for name in sorted(os.listdir(dataset_dir)):
        if name.startswith("filings_") and name.endswith(".json"):
            scopes.append(name[len("filings_") : -len(".json")])
    return scopes


def flatten_filing(scope: str, filing: Dict[str, Any], dataset_dir: str) -> Dict[str, Any]:
    meta = filing.get("metadata") or {}
    stats = filing.get("_doc_stats") or {}
    party1 = meta.get("party_1") or {}
    party2 = meta.get("party_2") or {}
    uid = filing.get("uid") or ""
    files_dir = os.path.join(dataset_dir, "files")
    html_htm = os.path.join(files_dir, f"{uid}.htm")
    html_html = os.path.join(files_dir, f"{uid}.html")
    html_path = html_htm if os.path.exists(html_htm) else (html_html if os.path.exists(html_html) else None)

    return {
        "scope": scope,
        "uid": uid,
        "formType": filing.get("formType"),
        # metadata
        "contract_type": meta.get("contract_type") or "Unknown",
        "version_type": meta.get("version_type") or None,
        "contract_date": meta.get("contract_date") or None,
        "is_amendment": meta.get("is_amendment"),
        "amendment_date": meta.get("amendment_date") or None,
        "amendment_number": meta.get("amendment_number") or None,
        "party_1_name": party1.get("name"),
        "party_2_name": party2.get("name"),
        "confidence": meta.get("confidence"),
        # stats and paths
        "doc_pages_estimate": int(stats.get("doc_pages_estimate")),
        "html_path": html_path,
    }


@st.cache_data(show_spinner=False)
def load_dataset_rows(dataset_dir: str) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    combined_path = os.path.join(dataset_dir, "filings.json")
    if os.path.exists(combined_path):
        try:
            filings = read_json(combined_path)
        except Exception:
            filings = []
        if isinstance(filings, list):
            for filing in filings:
                scope = str(filing.get("scope") or "unknown")
                rows.append(flatten_filing(scope, filing, dataset_dir))
    else:
        for scope in list_scopes_flat(dataset_dir):
            filings_path = os.path.join(dataset_dir, f"filings_{scope}.json")
            try:
                filings = read_json(filings_path)
            except Exception:
                filings = []
            if isinstance(filings, list):
                for filing in filings:
                    rows.append(flatten_filing(scope, filing, dataset_dir))
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def main() -> None:
    st.set_page_config(page_title="EDGAR Contract Metadata", layout="wide")
    st.title("EDGAR Contract Dataset – Metadata Browser")

    dataset_dir = "dataset"

    df = load_dataset_rows(dataset_dir)
    if df.empty:
        st.info("No dataset found. Provide either `dataset/filings.json` (normalized) or one/more `dataset/filings_<scope>.json` files. Ensure HTMLs are under `dataset/files/`.")
        return

    # Prepare filter choices
    all_contract_types = sorted([x for x in df["contract_type"].dropna().unique().tolist()])

    with st.sidebar:
        st.header("Filters")
        contract_type_selected = st.multiselect(
            "Contract type",
            options=all_contract_types,
            default=all_contract_types,
        )
        is_amendment_choice = st.selectbox(
            "Is amendment",
            options=["All", True, False],
            index=0,
        )

    # Apply filters
    filtered = df.copy()
    if contract_type_selected:
        filtered = filtered[filtered["contract_type"].isin(contract_type_selected)]
    if is_amendment_choice != "All":
        filtered = filtered[filtered["is_amendment"] == is_amendment_choice]

    st.caption(f"Showing {len(filtered)} of {len(df)} documents")

    tab_table, tab_chart, tab_viewer = st.tabs(["Table", "Bar chart (stacked)", "Viewer"]) 

    with tab_table:
        display_cols = [
            "uid",
            "formType",
            "contract_type",
            "version_type",
            "contract_date",
            "is_amendment",
            "amendment_date",
            "amendment_number",
            "party_1_name",
            "party_2_name",
            "confidence",
            "doc_pages_estimate",
            "html_path",
        ]
        display_cols = [c for c in display_cols if c in filtered.columns]
        st.dataframe(filtered[display_cols], use_container_width=True)

        csv_bytes = filtered[display_cols].to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download CSV",
            data=csv_bytes,
            file_name="filtered_filings.csv",
            mime="text/csv",
        )

    with tab_chart:
        # Only consider rows where is_amendment is boolean for the stacked breakdown
        chart_df = filtered.copy()
        chart_df = chart_df[chart_df["is_amendment"].isin([True, False])]
        # Ensure contract_type exists
        chart_df["contract_type"] = chart_df["contract_type"].fillna("Unknown")
        # Aggregate counts
        grouped = (
            chart_df.groupby(["contract_type", "is_amendment"]).size().reset_index(name="count")
        )
        if grouped.empty:
            st.info("No data available for chart (check filters).")
        else:
            # Sort x-axis by total count descending
            totals = grouped.groupby("contract_type")["count"].sum().reset_index()
            totals = totals.sort_values("count", ascending=False)
            contract_order = totals["contract_type"].tolist()

            chart = (
                alt.Chart(grouped)
                .mark_bar()
                .encode(
                    x=alt.X("contract_type:N", sort=contract_order, title="Contract type"),
                    y=alt.Y("count:Q", title="# Documents"),
                    color=alt.Color(
                        "is_amendment:N",
                        title="Is amendment",
                        scale=alt.Scale(domain=[False, True], range=["#4C78A8", "#F58518"]),
                    ),
                    tooltip=["contract_type", "is_amendment", "count"],
                )
                .properties(height=420)
            )
            st.altair_chart(chart, use_container_width=True)

    with tab_viewer:
        st.subheader("Document Viewer")
        if filtered.empty:
            st.info("No documents in current filter.")
        else:
            col_conf_w, col_conf_h = st.columns(2)
            with col_conf_w:
                viewer_width = st.number_input(
                    "Viewer width (px)", min_value=600, max_value=2400, value=1500, step=50
                )
            with col_conf_h:
                viewer_height = st.number_input(
                    "Viewer height (px)", min_value=400, max_value=2000, value=1000, step=50
                )
            # Build labeled options: "uid / contract_type / is_amendment"
            opts_df = filtered.copy()
            opts_df["uid"] = opts_df["uid"].astype(str)
            opts_df["contract_type"] = opts_df["contract_type"].fillna("Unknown").astype(str)
            def _amend_str(v):
                return "True" if v is True else ("False" if v is False else "Unknown")
            opts_df["is_amendment_str"] = opts_df["is_amendment"].apply(_amend_str)
            opts_df = opts_df.drop_duplicates(subset=["uid"], keep="first")
            options = [
                {
                    "uid": r["uid"],
                    "label": f"{r['uid']} / {r['contract_type']} / {r['is_amendment_str']}",
                }
                for _, r in opts_df[["uid", "contract_type", "is_amendment_str"]].iterrows()
            ]
            if not options:
                st.info("No documents to select.")
                return
            default_idx = 0
            if "viewer_uid" in st.session_state:
                for idx, rec in enumerate(options):
                    if rec["uid"] == st.session_state["viewer_uid"]:
                        default_idx = idx
                        break
            selected_label = st.selectbox(
                "Select document (uid / contract type / is amendment)",
                options=[rec["label"] for rec in options],
                index=default_idx,
            )
            # Resolve selected uid
            selected_uid = next((rec["uid"] for rec in options if rec["label"] == selected_label), None)
            if selected_uid:
                st.session_state["viewer_uid"] = selected_uid
                # Find the first matching row
                row = filtered[filtered["uid"].astype(str) == selected_uid]
                if row.empty:
                    st.warning("Selected UID not found in the filtered set.")
                else:
                    row = row.iloc[0]
                    html_path = row.get("html_path")
                    if not html_path or not os.path.exists(html_path):
                        # Try constructing from shared files dir
                        files_dir = os.path.join(dataset_dir, "files")
                        candidate_htm = os.path.join(files_dir, f"{selected_uid}.htm")
                        candidate_html = os.path.join(files_dir, f"{selected_uid}.html")
                        html_path = candidate_htm if os.path.exists(candidate_htm) else (
                            candidate_html if os.path.exists(candidate_html) else None
                        )
                    if not html_path:
                        st.warning("HTML file not found for this UID.")
                    else:
                        try:
                            with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
                                html_content = f.read()
                            components.html(html_content, width=int(viewer_width), height=int(viewer_height), scrolling=True)
                        except Exception as e:
                            st.error(f"Failed to render HTML: {e}")


if __name__ == "__main__":
    main()


