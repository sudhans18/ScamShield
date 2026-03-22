from __future__ import annotations

from typing import Any

from app.services.supabase_client import supabase


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    text = str(value).strip()
    return [text] if text else []


def create_entity(entity_type: str, value: str) -> dict[str, Any]:
    """Create or fetch an entity node by (entity_type, value)."""
    normalized_type = (entity_type or "").strip().lower()
    normalized_value = (value or "").strip()
    if not normalized_type or not normalized_value:
        raise ValueError("entity_type and value are required")

    existing = (
        supabase.table("entities")
        .select("id, entity_type, value")
        .eq("entity_type", normalized_type)
        .eq("value", normalized_value)
        .limit(1)
        .execute()
    )
    if existing.data:
        return existing.data[0]

    created = (
        supabase.table("entities")
        .insert({"entity_type": normalized_type, "value": normalized_value})
        .execute()
    )
    if created.data:
        return created.data[0]

    return {"entity_type": normalized_type, "value": normalized_value}


def create_relationship(source_id: str, target_id: str, relationship_type: str) -> dict[str, Any] | None:
    """Create or fetch a typed relationship edge between 2 entities."""
    rel_type = (relationship_type or "").strip().lower()
    src = (source_id or "").strip()
    dst = (target_id or "").strip()
    if not src or not dst or not rel_type or src == dst:
        return None

    existing = (
        supabase.table("entity_relationships")
        .select("id, source_id, target_id, relationship_type")
        .eq("source_id", src)
        .eq("target_id", dst)
        .eq("relationship_type", rel_type)
        .limit(1)
        .execute()
    )
    if existing.data:
        return existing.data[0]

    created = (
        supabase.table("entity_relationships")
        .insert(
            {
                "source_id": src,
                "target_id": dst,
                "relationship_type": rel_type,
            }
        )
        .execute()
    )
    if created.data:
        return created.data[0]
    return None


def _build_edges(entities_dict: dict[str, Any]) -> list[tuple[tuple[str, str], str, tuple[str, str]]]:
    """Convert extracted NER entities into graph edge triples."""
    companies = _as_list(entities_dict.get("company"))
    phones = _as_list(entities_dict.get("phones") or entities_dict.get("phone"))
    locations = _as_list(entities_dict.get("location"))
    people = _as_list(entities_dict.get("agent") or entities_dict.get("person"))
    upis = _as_list(entities_dict.get("upi") or entities_dict.get("upi_id") or entities_dict.get("upi_ids"))

    triples: list[tuple[tuple[str, str], str, tuple[str, str]]] = []
    for company in companies:
        for phone in phones:
            triples.append((("company", company), "contact_phone", ("phone", phone)))
        for location in locations:
            triples.append((("company", company), "located_in", ("location", location)))
        for person in people:
            triples.append((("company", company), "hr_contact", ("person", person)))
        for upi in upis:
            triples.append((("company", company), "payment_upi", ("upi", upi)))

    for phone in phones:
        for upi in upis:
            triples.append((("phone", phone), "uses_upi", ("upi", upi)))

    # De-duplicate while preserving order.
    return list(dict.fromkeys(triples))


def store_message_graph(entities_dict: dict[str, Any]) -> dict[str, Any]:
    """Persist nodes and edges in Supabase and return a graph object."""
    edges = _build_edges(entities_dict)
    nodes_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    relationships: list[dict[str, Any]] = []

    for source_key, relation, target_key in edges:
        if source_key not in nodes_by_key:
            nodes_by_key[source_key] = create_entity(source_key[0], source_key[1])
        if target_key not in nodes_by_key:
            nodes_by_key[target_key] = create_entity(target_key[0], target_key[1])

        source_id = str(nodes_by_key[source_key].get("id") or "")
        target_id = str(nodes_by_key[target_key].get("id") or "")
        if not source_id or not target_id:
            continue

        relationship = create_relationship(source_id, target_id, relation)
        if relationship:
            relationships.append(relationship)

    graph_nodes = [
        {
            "id": node.get("id"),
            "entity_type": node.get("entity_type") or key[0],
            "value": node.get("value") or key[1],
        }
        for key, node in nodes_by_key.items()
    ]

    graph_edges = [
        {
            "id": rel.get("id"),
            "source_id": rel.get("source_id"),
            "target_id": rel.get("target_id"),
            "relationship_type": rel.get("relationship_type"),
        }
        for rel in relationships
    ]

    return {
        "nodes": graph_nodes,
        "edges": graph_edges,
    }
