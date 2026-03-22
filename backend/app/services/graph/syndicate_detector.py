from __future__ import annotations

import hashlib
from collections import defaultdict, deque
from typing import Any

from app.services.supabase_client import supabase


def _parse_entity_key(value: str) -> tuple[str, str]:
    text = str(value or "").strip()
    if not text:
        return "", ""
    if ":" not in text:
        return "unknown", text
    entity_type, entity_value = text.split(":", 1)
    return entity_type.strip().lower(), entity_value.strip()


def _build_entity_key(entity_type: str, entity_value: str) -> str:
    return f"{entity_type.strip().lower()}:{entity_value.strip()}"


def _chunk(values: list[str], size: int = 200) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def load_graph_edges() -> list[tuple[str, str]]:
    """Load graph edges from entity_relationships, returning entity-key pairs."""
    edge_rows = supabase.table("entity_relationships").select("*").execute().data or []
    if not edge_rows:
        return []

    id_set: set[str] = set()
    for row in edge_rows:
        for id_key in ("source_id", "target_id"):
            raw_id = str(row.get(id_key) or "").strip()
            if raw_id:
                id_set.add(raw_id)

    id_to_key: dict[str, str] = {}
    if id_set:
        id_list = list(id_set)
        for id_chunk in _chunk(id_list):
            entity_rows = (
                supabase.table("entities")
                .select("id, entity_type, value")
                .in_("id", id_chunk)
                .execute()
                .data
                or []
            )
            for entity in entity_rows:
                entity_id = str(entity.get("id") or "").strip()
                entity_type = str(entity.get("entity_type") or "").strip().lower()
                entity_value = str(entity.get("value") or "").strip()
                if entity_id and entity_type and entity_value:
                    id_to_key[entity_id] = _build_entity_key(entity_type, entity_value)

    edges: list[tuple[str, str]] = []
    for row in edge_rows:
        source_entity = str(row.get("source_entity") or "").strip()
        target_entity = str(row.get("target_entity") or "").strip()

        if not source_entity:
            source_id = str(row.get("source_id") or "").strip()
            source_entity = id_to_key.get(source_id, "")

        if not target_entity:
            target_id = str(row.get("target_id") or "").strip()
            target_entity = id_to_key.get(target_id, "")

        if source_entity and target_entity:
            edges.append((source_entity, target_entity))

    return edges


def build_adjacency_graph(edges: list[tuple[str, str]]) -> dict[str, set[str]]:
    """Build an undirected adjacency graph from edge pairs."""
    adjacency: dict[str, set[str]] = defaultdict(set)
    for source, target in edges:
        if source == target:
            continue
        adjacency[source].add(target)
        adjacency[target].add(source)
    return adjacency


def connected_components(adjacency: dict[str, set[str]]) -> list[set[str]]:
    """Return connected components as sets of node keys."""
    components: list[set[str]] = []
    visited: set[str] = set()

    for node in adjacency:
        if node in visited:
            continue

        component: set[str] = set()
        queue: deque[str] = deque([node])
        visited.add(node)

        while queue:
            current = queue.popleft()
            component.add(current)
            for neighbor in adjacency.get(current, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        if component:
            components.append(component)

    return components


def _cluster_risk_score(phone_count: int, upi_count: int, cluster_size: int) -> float:
    score = 0.35
    if phone_count >= 2:
        score += 0.2
    if phone_count >= 3:
        score += 0.15
    if upi_count >= 1:
        score += 0.15
    if cluster_size >= 6:
        score += 0.1
    return round(min(1.0, score), 2)


def _extract_cluster_payload(component: set[str]) -> dict[str, Any]:
    phones: list[str] = []
    upis: list[str] = []
    entities: list[str] = []

    for key in sorted(component):
        entity_type, entity_value = _parse_entity_key(key)
        if not entity_type or not entity_value:
            continue
        entities.append(key)
        if entity_type == "phone":
            phones.append(entity_value)
        if entity_type == "upi":
            upis.append(entity_value)

    unique_phones = sorted(set(phones))
    unique_upis = sorted(set(upis))

    qualifies = len(unique_phones) >= 3 or (len(unique_phones) >= 2 and len(unique_upis) >= 1)
    return {
        "is_potential_syndicate": qualifies,
        "cluster_size": len(entities),
        "phones": unique_phones,
        "upis": unique_upis,
        "entities": entities,
        "risk_score": _cluster_risk_score(len(unique_phones), len(unique_upis), len(entities)),
    }


def _cluster_fingerprint(entities: list[str]) -> str:
    source = "|".join(sorted(set(entities)))
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def store_syndicate_results(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Persist potential syndicates and members in Supabase."""
    persisted: list[dict[str, Any]] = []

    for cluster in clusters:
        entities = [str(item).strip() for item in cluster.get("entities", []) if str(item).strip()]
        if not entities:
            continue

        fingerprint = _cluster_fingerprint(entities)
        existing = (
            supabase.table("syndicates")
            .select("id")
            .eq("fingerprint", fingerprint)
            .limit(1)
            .execute()
            .data
            or []
        )

        syndicate_id: Any
        if existing:
            syndicate_id = existing[0].get("id")
            (
                supabase.table("syndicates")
                .update(
                    {
                        "cluster_size": int(cluster.get("cluster_size") or 0),
                        "phones": cluster.get("phones", []),
                        "entities": entities,
                        "risk_score": float(cluster.get("risk_score") or 0),
                        "status": "potential",
                    }
                )
                .eq("id", syndicate_id)
                .execute()
            )
        else:
            inserted = (
                supabase.table("syndicates")
                .insert(
                    {
                        "fingerprint": fingerprint,
                        "cluster_size": int(cluster.get("cluster_size") or 0),
                        "phones": cluster.get("phones", []),
                        "entities": entities,
                        "risk_score": float(cluster.get("risk_score") or 0),
                        "status": "potential",
                    }
                )
                .execute()
                .data
                or []
            )
            syndicate_id = inserted[0].get("id") if inserted else None

        if not syndicate_id:
            continue

        member_rows: list[dict[str, Any]] = []
        for key in entities:
            entity_type, entity_value = _parse_entity_key(key)
            if not entity_type or not entity_value:
                continue
            member_rows.append(
                {
                    "syndicate_id": syndicate_id,
                    "entity_type": entity_type,
                    "entity_value": entity_value,
                    "entity_key": key,
                }
            )

        if member_rows:
            try:
                supabase.table("syndicate_members").upsert(
                    member_rows,
                    on_conflict="syndicate_id,entity_key",
                ).execute()
            except Exception:
                # If upsert constraints are unavailable, use insert best-effort.
                supabase.table("syndicate_members").insert(member_rows).execute()

        persisted.append(
            {
                "syndicate_id": syndicate_id,
                "cluster_size": int(cluster.get("cluster_size") or 0),
                "phones": cluster.get("phones", []),
                "entities": entities,
                "risk_score": float(cluster.get("risk_score") or 0),
            }
        )

    return persisted


def detect_and_store_syndicates() -> list[dict[str, Any]]:
    """Run full connected-component detection pipeline and persist qualifying clusters."""
    edges = load_graph_edges()
    if not edges:
        return []

    adjacency = build_adjacency_graph(edges)
    components = connected_components(adjacency)

    potential_clusters: list[dict[str, Any]] = []
    for component in components:
        payload = _extract_cluster_payload(component)
        if payload["is_potential_syndicate"]:
            potential_clusters.append(
                {
                    "cluster_size": payload["cluster_size"],
                    "phones": payload["phones"],
                    "entities": payload["entities"],
                    "risk_score": payload["risk_score"],
                }
            )

    if not potential_clusters:
        return []

    return store_syndicate_results(potential_clusters)


def entity_belongs_to_syndicate(entities_dict: dict[str, Any]) -> bool:
    """Check whether any extracted entity is already associated with a syndicate."""
    candidate_pairs: list[tuple[str, str]] = []

    phones = entities_dict.get("phones") or entities_dict.get("phone") or []
    upis = entities_dict.get("upi") or entities_dict.get("upi_id") or entities_dict.get("upi_ids") or []

    if not isinstance(phones, list):
        phones = [phones]
    if not isinstance(upis, list):
        upis = [upis]

    candidate_pairs.extend(
        [("phone", str(item).strip()) for item in phones if str(item).strip()]
    )
    candidate_pairs.extend(
        [("upi", str(item).strip()) for item in upis if str(item).strip()]
    )

    for entity_type, entity_value in candidate_pairs:
        rows = (
            supabase.table("syndicate_members")
            .select("syndicate_id")
            .eq("entity_type", entity_type)
            .eq("entity_value", entity_value)
            .limit(1)
            .execute()
            .data
            or []
        )
        if rows:
            return True

    return False
