from __future__ import annotations

import ast
import logging
from typing import Any

import numpy as np

from app.services.supabase_client import supabase


logger = logging.getLogger(__name__)

_MODEL: Any = None
_MODEL_NAME = "sentence-transformers/LaBSE"


def _get_model() -> Any:
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer

        _MODEL = SentenceTransformer(_MODEL_NAME)
    return _MODEL


def _parse_vector(raw: Any) -> np.ndarray | None:
    if raw is None:
        return None
    if isinstance(raw, list):
        try:
            return np.asarray([float(value) for value in raw], dtype=np.float32)
        except (TypeError, ValueError):
            return None
    if isinstance(raw, str):
        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, list):
                return np.asarray([float(value) for value in parsed], dtype=np.float32)
        except (ValueError, SyntaxError, TypeError):
            return None
    return None


def _safe_cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _fetch_centroids() -> tuple[np.ndarray | None, np.ndarray | None]:
    rows = supabase.table("cluster_centroids").select("cluster_name,centroid").execute().data or []
    legit: np.ndarray | None = None
    scam: np.ndarray | None = None
    for row in rows:
        name = str(row.get("cluster_name") or "").strip().lower()
        vector = _parse_vector(row.get("centroid"))
        if vector is None:
            continue
        if name == "legitimate":
            legit = vector
        elif name == "scam":
            scam = vector
    return legit, scam


def compute_embedding_score(text: str) -> dict[str, Any]:
    """
    Compute semantic distance from legitimate/scam centroids.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return {
            "embedding_score": 0.5,
            "sim_to_legitimate": 0.0,
            "sim_to_scam": 0.0,
            "boundary_distance": 0.0,
            "status": "empty_input",
        }

    try:
        model = _get_model()
        vector = model.encode(cleaned, normalize_embeddings=True)
        message_vec = np.asarray(vector, dtype=np.float32)
    except Exception as exc:
        logger.warning("embedding_scorer: model encode failed - %s", exc)
        return {
            "embedding_score": 0.5,
            "sim_to_legitimate": 0.0,
            "sim_to_scam": 0.0,
            "boundary_distance": 0.0,
            "status": "model_unavailable",
        }

    legit_centroid, scam_centroid = _fetch_centroids()
    if legit_centroid is None or scam_centroid is None:
        return {
            "embedding_score": 0.5,
            "sim_to_legitimate": 0.0,
            "sim_to_scam": 0.0,
            "boundary_distance": 0.0,
            "status": "centroids_missing",
        }

    sim_legit = _safe_cosine_similarity(message_vec, legit_centroid)
    sim_scam = _safe_cosine_similarity(message_vec, scam_centroid)
    boundary_distance = abs(sim_scam - sim_legit)
    embedding_score = (sim_scam - sim_legit + 1.0) / 2.0
    embedding_score = max(0.0, min(1.0, embedding_score))

    return {
        "embedding_score": round(float(embedding_score), 4),
        "sim_to_legitimate": round(float(sim_legit), 4),
        "sim_to_scam": round(float(sim_scam), 4),
        "boundary_distance": round(float(boundary_distance), 4),
        "status": "ok",
    }
