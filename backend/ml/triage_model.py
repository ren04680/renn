"""Triage classifier: TF-IDF (word 1-2 + char 2-5) + Logistic Regression, one head for specialty,
one for urgency. Trained by scripts/train_triage.py, loaded here for inference + explanations."""
from __future__ import annotations

import threading

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

from backend.config import TRIAGE_MODEL_PATH

_lock = threading.Lock()
_model = None


def make_pipeline(class_weight=None) -> Pipeline:
    feats = FeatureUnion([
        ("word", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1)),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, min_df=2)),
    ])
    return Pipeline([("tfidf", feats), ("lr", LogisticRegression(C=8.0, max_iter=3000, class_weight=class_weight))])


def load():
    global _model
    with _lock:
        if _model is None:
            import joblib

            if not TRIAGE_MODEL_PATH.exists():
                raise FileNotFoundError(
                    f"{TRIAGE_MODEL_PATH} missing — run `python -m scripts.train_triage` first"
                )
            _model = joblib.load(TRIAGE_MODEL_PATH)
        return _model


def _explain(pipe: Pipeline, text: str, cls_idx: int, k: int = 4) -> list[str]:
    feats: FeatureUnion = pipe.named_steps["tfidf"]
    lr: LogisticRegression = pipe.named_steps["lr"]
    x = feats.transform([text])
    names = feats.get_feature_names_out()
    coef = lr.coef_[cls_idx] if lr.coef_.shape[0] > 1 else lr.coef_[0]
    row = x.tocoo()
    contrib = [(row.data[i] * coef[row.col[i]], names[row.col[i]]) for i in range(len(row.data))]
    contrib.sort(reverse=True)
    out = []
    for c, n in contrib:
        if c <= 0:
            break
        if n.startswith("word__"):
            out.append(n[6:])
        if len(out) >= k:
            break
    return out


def classify(text: str) -> dict:
    m = load()
    sp: Pipeline = m["specialty"]
    ur: Pipeline = m["urgency"]
    ps = sp.predict_proba([text])[0]
    pu = ur.predict_proba([text])[0]
    si = int(np.argmax(ps))
    ui = int(np.argmax(pu))
    order = np.argsort(-ps)[:3]
    return {
        "specialty": sp.classes_[si],
        "specialty_conf": round(float(ps[si]), 3),
        "urgency": ur.classes_[ui],
        "urgency_conf": round(float(pu[ui]), 3),
        "emergency_prob": round(float(pu[list(ur.classes_).index("emergency")]), 3),
        "top3": [{"specialty": sp.classes_[i], "p": round(float(ps[i]), 3)} for i in order],
        "evidence": _explain(sp, text, si),
        "model": m.get("name", "tfidf+lr"),
    }
