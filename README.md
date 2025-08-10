## Edgar demo

Minimal example that searches SEC filings using `sec-api` and downloads the first result.

### Prerequisites
- Python 3.9+

### Installation
1) Create and activate a virtual environment (recommended).
   - PowerShell:
     ```powershell
python -m venv .venv
. .venv/Scripts/Activate.ps1
     ```
2) Install dependencies:
   ```bash
pip install -r requirements.txt
   ```

### Configure environment variables
Create a `.env` file in the project root with your SEC API key (or copy `.env.example` to `.env` and fill your key):
```env
SEC_API_KEY=YOUR_SEC_API_KEY_HERE
```

Notes:
- Do not commit real secrets. In git, add `.env` to `.gitignore`.
- On Windows, you can also set a session env var in PowerShell:
  ```powershell
  $env:SEC_API_KEY="your_key_here"
  ```

### Run
```bash
python demo.py
```

### Troubleshooting
- If you see "Environment variable SEC_API_KEY is not set", ensure `.env` exists and that `python-dotenv` is installed (it is included in `requirements.txt`).
