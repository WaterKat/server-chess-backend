@echo off
if not exist .\.venv (
  python -m venv .\.venv
)

.venv\Scripts\pip.exe install -r requirements.txt
.venv\Scripts\python.exe app.py
