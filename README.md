## EDGAR Contract Dataset Builder

This module builds a dataset of legal contracts from the SEC EDGAR database and provides a Streamlit app to explore the results.

What it does:
- 1) Search and download filings from EDGAR using a full-text query and optional keyword filtering on the downloaded HTML.
- 2) Use an LLM to analyze each document and extract structured contract metadata.
- 3) Normalize contract types and browse the results in a Streamlit app.

### Requirements
- Python 3.9+

### Install
```bash
python -m venv .venv
source .venv/bin/activate   # Windows PowerShell: . .venv/Scripts/Activate.ps1
pip install -r requirements.txt
```

### Configure API keys (.env)
Create a `.env` file in the project root with the required API keys. Both tools will automatically load it.
```env
# Required for search & download (sec-api.com)
SEC_API_KEY=your_sec_api_key

# Required for LLM metadata extraction (OpenAI)
OPENAI_API_KEY=your_openai_api_key
```

Notes:
- Do not commit real secrets. Keep `.env` out of version control.
- You may also export these variables in your shell instead of using `.env`.

### Prepare scopes (search configuration)
Edit `scope.json` to define one or more search scopes. Each scope describes a full-text EDGAR query, date range, and optional keyword filter applied to downloaded HTML.

Example `scope.json`:
```json
[
  {
    "type": "derivatives",
    "search": "(ISDA OR \"Master Agreement\") AND exhibit",
    "start": 2021,
    "end": 2024,
    "keywords": ["ISDA", "Master"]
  }
]
```

### Run the pipeline (in order)
1) Search EDGAR and download filtered filings (HTML):
```bash
python search.py --scope-file scope.json --output-dir dataset --forms 8-K 10-Q --delay-ms 200
```
Outputs:
- `dataset/files/<uid>.htm` HTML files
- `dataset/filings_<scope>.json` metadata for selected filings per scope

2) Extract contract metadata with an LLM:
```bash
python metadata.py --scope-file scope.json --dataset-dir dataset --model gpt-4o-mini --max-words 900
```
Notes:
- Set `--overwrite` to re-extract for filings that already have metadata.
- Choose an OpenAI model available to your account (the code defaults to `gpt-5-mini` but you can override as above).

3) Normalize contract types and combine all scopes:
```bash
python normalize.py --dataset-dir dataset --mapping-file normalize.json --output dataset/filings.json
```
Outputs:
- `dataset/filings.json` combined, normalized dataset (includes a `scope` field). The normalization removes `metadata.contract_category` and sets `metadata.contract_type` to a normalized value.

### Explore in Streamlit
Run the app and browse the dataset:
```bash
streamlit run app.py
```
The app will automatically:
- Load `dataset/filings.json` if present; otherwise it falls back to all `dataset/filings_<scope>.json` files.
- Provide filters for contract type and whether the document is an amendment.
- Display a table, a stacked bar chart, and an HTML viewer for the selected document.

### Data layout
- `dataset/files/` contains HTML files named `<uid>.htm` or `<uid>.html`.
- `dataset/filings_<scope>.json` contains a list of filings for a given scope.
- `dataset/filings.json` is the combined, normalized dataset produced by `normalize.py`.

### Troubleshooting
- Missing SEC key: ensure `SEC_API_KEY` is set in `.env` or the environment before running `search.py`.
- Missing OpenAI key: ensure `OPENAI_API_KEY` is set in `.env` or the environment before running `metadata.py`.
- Empty Streamlit app: verify that either `dataset/filings.json` exists or that one or more `dataset/filings_<scope>.json` files were created, and that `dataset/files/` contains the HTMLs.
