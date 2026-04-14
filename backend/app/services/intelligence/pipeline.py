from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.services.graph.consistency_checker import run_full_consistency_check
from app.services.graph.graph_service import store_message_graph
from app.services.graph.syndicate_detector import detect_and_store_syndicates
from app.services.intelligence.embedding_scorer import compute_embedding_score
from app.services.intelligence.entity_extractor import extract_entities
from app.services.intelligence.llm_investigator import investigate_with_llm
from app.services.propagation.propagation_analyzer import analyze_propagation


_EXECUTOR = ThreadPoolExecutor(max_workers=4)


def _risk_level_from_score(score: float) -> str:
    if score < 0.35:
        return "LOW"
    if score <= 0.65:
        return "MEDIUM"
    return "HIGH"


def _normalize_entities_for_output(entities: dict[str, Any]) -> dict[str, Any]:
    phones = entities.get("phones") or []
    if not isinstance(phones, list):
        phones = [phones]
    upi_ids = entities.get("upi_ids") or []
    if not isinstance(upi_ids, list):
        upi_ids = [upi_ids]

    return {
        "phones": [str(item).strip() for item in phones if str(item).strip()],
        "phone": [str(item).strip() for item in phones if str(item).strip()],
        "salary": entities.get("salary"),
        "fee": entities.get("fee"),
        "role": entities.get("role"),
        "location": entities.get("location"),
        "agent": entities.get("agent"),
        "company": entities.get("company"),
        "upi_ids": [str(item).strip() for item in upi_ids if str(item).strip()],
        "upi": [str(item).strip() for item in upi_ids if str(item).strip()],
        "urgency_flags": entities.get("urgency_flags") or [],
        "has_fee": bool(entities.get("has_fee")),
        "has_urgency": bool(entities.get("has_urgency")),
    }


def _consistency_sync(entities: dict[str, Any]) -> dict[str, Any]:
    return run_full_consistency_check(entities, {"nodes": [], "edges": []})


def _propagation_sync(text: str, forwarded_many_times: bool, source_channel: str) -> dict[str, Any]:
    return analyze_propagation(text, forwarded_many_times=forwarded_many_times, source_channel=source_channel)


async def _store_graph_async(entities: dict[str, Any]) -> None:
    def _task() -> None:
        try:
            store_message_graph(entities)
            detect_and_store_syndicates()
        except Exception:
            return

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_EXECUTOR, _task)


def _build_reasons(
    llm_result: dict[str, Any],
    consistency_result: dict[str, Any],
    propagation_result: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    reasoning = str(llm_result.get("reasoning") or "").strip()
    key_contradiction = llm_result.get("key_contradiction")
    if reasoning:
        reasons.append(reasoning)
    if key_contradiction:
        reasons.append(str(key_contradiction))

    for detail in consistency_result.get("contradiction_details") or []:
        if isinstance(detail, str) and detail.strip():
            reasons.append(detail.strip())
        if len(reasons) >= 4:
            break

    for signal in propagation_result.get("signals") or []:
        if isinstance(signal, str) and signal.strip():
            reasons.append(signal.replace("_", " "))
        if len(reasons) >= 5:
            break

    deduped: list[str] = []
    seen: set[str] = set()
    for reason in reasons:
        key = reason.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(reason)
    return deduped[:5] or ["No major contradiction identified."]


def _build_final_result(
    text: str,
    entities: dict[str, Any],
    embedding_result: dict[str, Any],
    consistency_result: dict[str, Any],
    propagation_result: dict[str, Any],
    llm_result: dict[str, Any],
    source_channel: str,
    media_context: dict | None,
) -> dict[str, Any]:
    risk_score = float(llm_result.get("risk_score") or 0.52)
    risk_level = _risk_level_from_score(risk_score)
    reasons = _build_reasons(llm_result, consistency_result, propagation_result)
    out_entities = _normalize_entities_for_output(entities)

    return {
        "risk_score": round(risk_score, 2),
        "risk_level": risk_level,
        "is_scam": risk_score >= 0.65,
        "verdict": llm_result.get("verdict", "SUSPICIOUS"),
        "confidence": int(llm_result.get("confidence") or 55),
        "reasons": reasons,
        "key_contradiction": llm_result.get("key_contradiction"),
        "hindi_worker_message": llm_result.get("hindi_worker_message"),
        "hindi_verdict": llm_result.get("hindi_worker_message"),
        "english_summary": str(llm_result.get("reasoning") or "").strip(),
        "entities": out_entities,
        "layer_scores": {
            "embedding": embedding_result.get("embedding_score"),
            "consistency_contradictions": consistency_result.get("contradictions"),
            "propagation": propagation_result.get("propagation_score"),
            "llm_confidence": int(llm_result.get("confidence") or 55),
        },
        "source": source_channel,
        "media_context": media_context or {},
        "input_text": text,
    }


async def run_intelligence_pipeline(
    text: str,
    forwarded_many_times: bool = False,
    source_channel: str = "dashboard",
    media_context: dict | None = None,
) -> dict[str, Any]:
    entities = extract_entities(text)
    loop = asyncio.get_running_loop()

    embedding_fut = loop.run_in_executor(_EXECUTOR, compute_embedding_score, text)
    consistency_fut = loop.run_in_executor(_EXECUTOR, _consistency_sync, entities)
    propagation_fut = loop.run_in_executor(
        _EXECUTOR,
        _propagation_sync,
        text,
        forwarded_many_times,
        source_channel,
    )

    embedding_result, consistency_result, propagation_result = await asyncio.gather(
        embedding_fut,
        consistency_fut,
        propagation_fut,
    )

    llm_result = await investigate_with_llm(
        text=text,
        entities=entities,
        embedding_result=embedding_result,
        consistency_result=consistency_result,
        propagation_result=propagation_result,
        media_context=media_context,
    )

    asyncio.create_task(_store_graph_async(_normalize_entities_for_output(entities)))

    return _build_final_result(
        text=text,
        entities=entities,
        embedding_result=embedding_result,
        consistency_result=consistency_result,
        propagation_result=propagation_result,
        llm_result=llm_result,
        source_channel=source_channel,
        media_context=media_context,
    )

