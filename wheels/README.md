# Offline Windows install pack (backup)

74 pre-built wheels for **Windows x64 + Python 3.13** (no compiler, no PyPI access needed).
`run.bat` uses this folder automatically when it exists. Manual equivalent:

```powershell
.venv\Scripts\python -m pip install --no-index --find-links wheels\wh -r wheels\req-win.txt
```
Only needed if `pip` cannot reach PyPI (SSL / firewall errors). Not part of the submission zip.
ChromaDB is not included (it needs an sdist); the app then uses its built-in vector store automatically.
