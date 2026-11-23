"""Assemble the submission/ folder: docs, dataset CSVs, model files + metrics, test results,
screenshots (already captured), and a source zip of every git-tracked file.

Run after `scripts/run_scenarios.py` and `scripts/capture_screenshots.py`:
  python -m scripts.build_submission
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUB = ROOT / "submission"


def main() -> None:
    SUB.mkdir(exist_ok=True)
    for f in ("README.md", "DEMO_SCRIPT.md", "DECISIONS.md"):
        shutil.copy(ROOT / f, SUB / f)
    (SUB / "data").mkdir(exist_ok=True)
    for f in (ROOT / "data").glob("*.csv"):
        shutil.copy(f, SUB / "data" / f.name)
    (SUB / "models").mkdir(exist_ok=True)
    for f in (ROOT / "models").iterdir():
        if f.is_file():
            shutil.copy(f, SUB / "models" / f.name)
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    files = [f for f in files if not f.startswith(("submission/", "wheels/"))]
    with zipfile.ZipFile(SUB / "source.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            p = ROOT / f
            if p.is_file():
                z.write(p, f"hospital-agent-os/{f}")
    shots = sorted((SUB / "screenshots").glob("*.png"))
    res = json.loads((SUB / "test_results.json").read_text(encoding="utf-8")) if (SUB / "test_results.json").exists() else {"results": []}
    met = json.loads((ROOT / "models" / "metrics.json").read_text(encoding="utf-8"))
    n_pass = sum(r["pass"] for r in res["results"])
    std = met["split_standard_80_20"]
    lines = [
        "# Submission — Hospital Agent OS", "",
        f"Assembled {time.strftime('%Y-%m-%d %H:%M')}.", "",
        "| Item | Location | Status |", "|---|---|---|",
        f"| Source code (all tracked files) | `source.zip` | ✅ {len(files)} files |",
        f"| Dataset (HIS tables + triage dataset) | `data/*.csv` | ✅ {len(list((SUB / 'data').glob('*.csv')))} CSVs |",
        "| Model file | `models/triage_classifier.joblib` | ✅ TF-IDF + Logistic Regression |",
        f"| Model metrics | `models/metrics.json`, `models/confusion_matrix.png` | ✅ specialty acc {std['specialty']['accuracy']:.3f}, macro-F1 {std['specialty']['macro_f1']:.3f}; emergency recall {std['urgency']['emergency_recall']:.3f} |",
        f"| Scenario test results | `test_results.md / .csv / .json` | ✅ {n_pass}/{len(res['results'])} passed |",
        f"| Step-by-step screenshots | `screenshots/NN_*.png` | ✅ {len(shots)} screenshots |",
        "| README (setup, architecture, Mermaid diagrams) | `README.md` | ✅ |",
        "| Live demo script + viva Q&A | `DEMO_SCRIPT.md` | ✅ |",
        "| Design decisions log | `DECISIONS.md` | ✅ |", "",
        "## Screenshots", "",
    ] + [f"{i + 1}. `{s.name}`" for i, s in enumerate(shots)]
    (SUB / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:16]))


if __name__ == "__main__":
    sys.exit(main())
