"""
Compute LaBSE embeddings for seeded corpora and write cluster centroids.

Run from repo root:
    python scripts/compute_centroids.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

from app.services.supabase_client import supabase  # noqa: E402


MODEL_NAME = "sentence-transformers/LaBSE"


def _vector_literal(values: np.ndarray) -> str:
    return "[" + ",".join(f"{float(x):.8f}" for x in values.tolist()) + "]"


def _parse_vector(raw: Any) -> list[float] | None:
    if raw is None:
        return None
    if isinstance(raw, list):
        try:
            return [float(item) for item in raw]
        except (TypeError, ValueError):
            return None
    if isinstance(raw, str):
        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, list):
                return [float(item) for item in parsed]
        except (ValueError, SyntaxError, TypeError):
            return None
    return None


def _fetch_rows(table: str) -> list[dict[str, Any]]:
    response = supabase.table(table).select("id,text,embedding").execute()
    return response.data or []


def _embed_missing_rows(model: SentenceTransformer, table: str) -> None:
    rows = _fetch_rows(table)
    missing = [row for row in rows if row.get("text") and row.get("embedding") is None]
    if not missing:
        print(f"No missing embeddings in {table}")
        return

    texts = [str(row["text"]) for row in missing]
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    for row, embedding in zip(missing, embeddings):
        vector = np.asarray(embedding, dtype=np.float32)
        supabase.table(table).update({"embedding": _vector_literal(vector)}).eq("id", row["id"]).execute()

    print(f"Embedded {len(missing)} rows for {table}")


def _load_embeddings(table: str) -> np.ndarray:
    rows = _fetch_rows(table)
    vectors: list[list[float]] = []
    for row in rows:
        parsed = _parse_vector(row.get("embedding"))
        if parsed:
            vectors.append(parsed)
    if not vectors:
        raise RuntimeError(f"No embeddings available in {table}. Seed data and embed first.")
    return np.asarray(vectors, dtype=np.float32)


def _upsert_centroid(cluster_name: str, centroid: np.ndarray, sample_count: int) -> None:
    payload = {
        "cluster_name": cluster_name,
        "centroid": _vector_literal(centroid),
        "sample_count": sample_count,
    }
    supabase.table("cluster_centroids").upsert(payload, on_conflict="cluster_name").execute()


def main() -> None:
    print(f"Loading embedding model: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)

    _embed_missing_rows(model, "job_postings_legitimate")
    _embed_missing_rows(model, "job_postings_scam")

    legit_vectors = _load_embeddings("job_postings_legitimate")
    scam_vectors = _load_embeddings("job_postings_scam")

    legit_centroid = np.mean(legit_vectors, axis=0)
    scam_centroid = np.mean(scam_vectors, axis=0)

    # Keep centroid vectors normalized for cosine similarity.
    legit_centroid /= np.linalg.norm(legit_centroid) or 1.0
    scam_centroid /= np.linalg.norm(scam_centroid) or 1.0

    _upsert_centroid("legitimate", legit_centroid, legit_vectors.shape[0])
    _upsert_centroid("scam", scam_centroid, scam_vectors.shape[0])

    print(
        "Centroids updated: "
        f"legitimate={legit_vectors.shape[0]} samples, "
        f"scam={scam_vectors.shape[0]} samples."
    )


if __name__ == "__main__":
    main()

