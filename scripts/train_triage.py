"""Generate the triage dataset and train the TF-IDF + Logistic Regression classifier.

Outputs:
  data/triage_dataset.csv
  models/triage_classifier.joblib
  models/metrics.json
  models/confusion_matrix.png
Run:  python -m scripts.train_triage
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import joblib  # noqa: E402
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score  # noqa: E402
from sklearn.model_selection import GroupShuffleSplit, train_test_split  # noqa: E402

from backend.config import DATA_DIR, MODELS_DIR, TRIAGE_MODEL_PATH  # noqa: E402
from backend.ml.triage_data import generate  # noqa: E402
from backend.ml.triage_model import make_pipeline  # noqa: E402


def evaluate(train: pd.DataFrame, test: pd.DataFrame) -> dict:
    out = {}
    for target, cw in (("specialty", None), ("urgency", "balanced")):
        p = make_pipeline(cw).fit(train.text, train[target])
        pred = p.predict(test.text)
        out[target] = {
            "accuracy": round(accuracy_score(test[target], pred), 4),
            "macro_f1": round(f1_score(test[target], pred, average="macro"), 4),
            "report": classification_report(test[target], pred, output_dict=True, zero_division=0),
            "labels": sorted(test[target].unique().tolist()),
            "cm": confusion_matrix(test[target], pred, labels=sorted(test[target].unique())).tolist(),
        }
        # emergency recall matters most for safety
        if target == "urgency":
            out[target]["emergency_recall"] = round(out[target]["report"].get("emergency", {}).get("recall", 0), 4)
    return out


def try_embeddings(train: pd.DataFrame, test: pd.DataFrame) -> dict:
    """Optional comparison: MiniLM sentence embeddings + LR. Skipped if the model is unavailable."""
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        from sklearn.linear_model import LogisticRegression

        st = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        Xtr = st.encode(train.text.tolist(), normalize_embeddings=True)
        Xte = st.encode(test.text.tolist(), normalize_embeddings=True)
        lr = LogisticRegression(max_iter=3000, C=8).fit(Xtr, train.specialty)
        pred = lr.predict(Xte)
        return {"status": "ok", "specialty_accuracy": round(accuracy_score(test.specialty, pred), 4),
                "specialty_macro_f1": round(f1_score(test.specialty, pred, average="macro"), 4)}
    except Exception as e:  # noqa: BLE001
        return {"status": "skipped", "reason": f"{type(e).__name__}: {str(e)[:160]}"}


def main() -> dict:
    t0 = time.time()
    rows = generate()
    df = pd.DataFrame(rows)
    df.to_csv(DATA_DIR / "triage_dataset.csv", index=False)
    print(f"dataset: {len(df)} rows  -> data/triage_dataset.csv")
    print(df.groupby(["specialty"]).size().to_dict())
    print(df.groupby(["urgency"]).size().to_dict(), df.groupby("language").size().to_dict())

    # 1) standard stratified split (in-distribution)
    tr, te = train_test_split(df, test_size=0.2, random_state=42, stratify=df.specialty + "_" + df.urgency)
    std = evaluate(tr, te)
    # 2) harder: unseen base phrases (group split) -> measures generalisation to new wordings
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    gi_tr, gi_te = next(gss.split(df, groups=df.phrase_id))
    grp = evaluate(df.iloc[gi_tr], df.iloc[gi_te])
    emb = try_embeddings(tr, te)

    # final models on all data
    spec = make_pipeline(None).fit(df.text, df.specialty)
    urg = make_pipeline("balanced").fit(df.text, df.urgency)
    chosen = "tfidf_word12_char25 + logistic_regression"
    if emb.get("status") == "ok" and emb["specialty_macro_f1"] > std["specialty"]["macro_f1"] + 0.01:
        chosen += " (embeddings scored higher but TF-IDF kept for offline/explainability)"
    joblib.dump({"specialty": spec, "urgency": urg, "name": "tfidf+lr", "trained_at": time.time(),
                 "n_train": len(df)}, TRIAGE_MODEL_PATH)

    metrics = {
        "model": chosen,
        "dataset_size": len(df),
        "class_counts": {"specialty": df.specialty.value_counts().to_dict(),
                         "urgency": df.urgency.value_counts().to_dict(),
                         "language": df.language.value_counts().to_dict()},
        "split_standard_80_20": {k: {kk: vv for kk, vv in v.items() if kk != "cm"} for k, v in std.items()},
        "split_unseen_phrases": {k: {kk: vv for kk, vv in v.items() if kk not in ("cm", "report")} for k, v in grp.items()},
        "embedding_comparison": emb,
        "train_seconds": round(time.time() - t0, 2),
    }
    (MODELS_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    fig, axes = plt.subplots(1, 2, figsize=(15, 6.2), gridspec_kw={"width_ratios": [1.6, 1]})
    for ax, key, title in ((axes[0], "specialty", "Specialty"), (axes[1], "urgency", "Urgency")):
        cm = np.array(std[key]["cm"])
        labels = std[key]["labels"]
        ax.imshow(cm, cmap="Blues")
        ax.set_xticks(range(len(labels)), [l.replace("_", " ") for l in labels], rotation=40, ha="right")
        ax.set_yticks(range(len(labels)), [l.replace("_", " ") for l in labels])
        for i in range(len(labels)):
            for j in range(len(labels)):
                ax.text(j, i, cm[i, j], ha="center", va="center",
                        color="white" if cm[i, j] > cm.max() / 2 else "#1f2937", fontsize=9)
        ax.set_xlabel("Predicted")
        ax.set_ylabel("True")
        ax.set_title(f"{title} — acc {std[key]['accuracy']:.3f}, macro-F1 {std[key]['macro_f1']:.3f}")
    fig.suptitle("Triage classifier (TF-IDF + LR) — held-out 20% test split", fontsize=13)
    fig.tight_layout()
    fig.savefig(MODELS_DIR / "confusion_matrix.png", dpi=130)
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk in ("accuracy", "macro_f1", "emergency_recall")}
                      for k, v in std.items()}, indent=1))
    print("unseen phrases:", {k: (v["accuracy"], v["macro_f1"]) for k, v in grp.items()})
    print("embeddings:", emb)
    return metrics


if __name__ == "__main__":
    main()
