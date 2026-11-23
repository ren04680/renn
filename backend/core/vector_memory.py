"""Unit 3 — long-term patient memory with vector retrieval.

Store: ChromaDB (persistent, cosine) — falls back to an in-process numpy index if chromadb is missing.
Embedder: sentence-transformers/all-MiniLM-L6-v2 when it can be loaded locally; otherwise a
deterministic hashing embedder (word + char n-grams + domain synonym expansion) that needs no
download. The choice is reported by `embedder_name()` and shown in the UI/trace.
"""
from __future__ import annotations

import re
import threading
import time
import uuid

import numpy as np

from backend.config import CHROMA_DIR, EMBEDDINGS

_SYNONYMS = {
    "usual": ["regular", "preferred", "always", "familiar", "same", "favourite"],
    "regular": ["usual", "preferred"],
    "doctor": ["dr", "physician", "consultant"],
    "dr": ["doctor"],
    "evening": ["pm", "after work", "late", "afternoon"],
    "morning": ["am", "early"],
    "tele": ["online", "video", "teleconsultation", "remote"],
    "online": ["tele", "video", "teleconsultation"],
    "video": ["tele", "online"],
    "prefers": ["likes", "preference", "wants"],
    "likes": ["prefers", "preference"],
    "knee": ["orthopedics", "joint", "bone"],
    "mother": ["mom", "mum", "maa", "family"],
    "visit": ["visited", "appointment", "seen"],
    "visited": ["visit", "appointment", "seen"],
}

_lock = threading.RLock()
_embedder = None
_embedder_name = None
_store = None


def _tokens(text: str) -> list[str]:
    toks = re.findall(r"[a-z0-9]+", text.lower())
    out = list(toks)
    for t in toks:
        out.extend(_SYNONYMS.get(t, []))
    return out


class HashingEmbedder:
    name = "hashing-ngrams-v1 (offline fallback)"

    def __init__(self) -> None:
        from sklearn.feature_extraction.text import HashingVectorizer

        self.word = HashingVectorizer(
            analyzer=lambda s: _tokens(s), n_features=2**11, alternate_sign=False, norm="l2"
        )
        self.char = HashingVectorizer(
            analyzer="char_wb", ngram_range=(3, 5), n_features=2**12, alternate_sign=False, norm="l2"
        )

    def __call__(self, texts: list[str]) -> list[list[float]]:
        w = self.word.transform(texts).toarray()
        c = self.char.transform(texts).toarray()
        v = np.hstack([w * 0.75, c * 0.66])
        n = np.linalg.norm(v, axis=1, keepdims=True)
        n[n == 0] = 1
        return (v / n).astype(np.float32).tolist()


class STEmbedder:
    name = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer  # type: ignore

        self.model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    def __call__(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, normalize_embeddings=True).tolist()


def get_embedder():
    global _embedder, _embedder_name
    with _lock:
        if _embedder is None:
            if EMBEDDINGS in ("auto", "minilm"):
                try:
                    _embedder = STEmbedder()
                except Exception:
                    _embedder = HashingEmbedder()
            else:
                _embedder = HashingEmbedder()
            _embedder_name = _embedder.name
        return _embedder


def embedder_name() -> str:
    get_embedder()
    return _embedder_name or "?"


class _NumpyStore:
    backend = "numpy (fallback)"

    def __init__(self) -> None:
        self.ids: list[str] = []
        self.vecs: list[list[float]] = []
        self.docs: list[str] = []
        self.metas: list[dict] = []

    def reset(self) -> None:
        self.__init__()

    def add(self, ids, embeddings, documents, metadatas) -> None:
        self.ids += ids
        self.vecs += embeddings
        self.docs += documents
        self.metas += metadatas

    def query(self, embedding, n, patient_id):
        idx = [i for i, m in enumerate(self.metas) if m.get("patient_id") == patient_id]
        if not idx:
            return []
        M = np.array([self.vecs[i] for i in idx])
        sims = M @ np.array(embedding)
        order = np.argsort(-sims)[:n]
        return [(self.ids[idx[o]], self.docs[idx[o]], self.metas[idx[o]], float(sims[o])) for o in order]


class _ChromaStore:
    backend = "chromadb"
    COLL = "patient_memory"

    def __init__(self) -> None:
        import chromadb

        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self.coll = self.client.get_or_create_collection(
            self.COLL, embedding_function=None, metadata={"hnsw:space": "cosine"}
        )

    def reset(self) -> None:
        try:
            self.client.delete_collection(self.COLL)
        except Exception:
            pass
        self.coll = self.client.get_or_create_collection(
            self.COLL, embedding_function=None, metadata={"hnsw:space": "cosine"}
        )

    def add(self, ids, embeddings, documents, metadatas) -> None:
        for i in range(0, len(ids), 500):
            self.coll.add(
                ids=ids[i : i + 500],
                embeddings=embeddings[i : i + 500],
                documents=documents[i : i + 500],
                metadatas=metadatas[i : i + 500],
            )

    def query(self, embedding, n, patient_id):
        res = self.coll.query(
            query_embeddings=[embedding], n_results=n, where={"patient_id": patient_id}
        )
        out = []
        for i, d, m, dist in zip(
            res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]
        ):
            out.append((i, d, m, 1.0 - float(dist)))
        return out


def get_store():
    global _store
    with _lock:
        if _store is None:
            try:
                _store = _ChromaStore()
            except Exception:
                _store = _NumpyStore()
        return _store


def store_backend() -> str:
    return get_store().backend


def rebuild_from_db() -> int:
    """(Re)index every Memory row. Called by the seed script and on API start-up."""
    from backend.db.models import Memory
    from backend.db.session import get_session

    with get_session() as s:
        rows = s.query(Memory).all()
        data = [(m.id, m.text, {"patient_id": m.patient_id, "kind": m.kind, "source": m.source}) for m in rows]
    with _lock:
        st = get_store()
        st.reset()
        if data:
            emb = get_embedder()([d[1] for d in data])
            st.add([d[0] for d in data], emb, [d[1] for d in data], [d[2] for d in data])
    return len(data)


def ensure_index() -> None:
    """Rebuild the index if it is empty (e.g. numpy fallback after a restart)."""
    st = get_store()
    try:
        empty = st.coll.count() == 0 if isinstance(st, _ChromaStore) else not st.ids
    except Exception:
        empty = True
    if empty:
        rebuild_from_db()


def add_memory(patient_id: str, text: str, kind: str, source: str) -> str:
    from backend.db.models import Memory
    from backend.db.session import get_session

    mid = "M" + uuid.uuid4().hex[:10]
    with get_session() as s:
        s.add(Memory(id=mid, patient_id=patient_id, text=text, kind=kind, source=source, created_at=time.time()))
    with _lock:
        emb = get_embedder()([text])
        get_store().add([mid], emb, [text], [{"patient_id": patient_id, "kind": kind, "source": source}])
    return mid


def search(patient_id: str, query: str, k: int = 4) -> list[dict]:
    with _lock:
        emb = get_embedder()([query])[0]
        hits = get_store().query(emb, k, patient_id)
    return [
        {"id": i, "text": d, "kind": m.get("kind"), "score": round(s, 3)} for (i, d, m, s) in hits
    ]
