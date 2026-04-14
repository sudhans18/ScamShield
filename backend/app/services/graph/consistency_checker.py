from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from app.services.graph.db_cross_checker import check_entity_consistency_against_db

_PHONE_RE = re.compile(r"^\+?[0-9]{10,15}$")


def _to_lower(value: Any) -> str:
    return str(value or "").strip().lower()


def _safe_float(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _is_valid_phone(phone_value: str) -> bool:
    cleaned = re.sub(r"[\s\-()]", "", str(phone_value or ""))
    return bool(_PHONE_RE.match(cleaned))


def _build_lookup(graph: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []

    node_by_id: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "").strip()
        if node_id:
            node_by_id[node_id] = node

    normalized_edges: list[dict[str, Any]] = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source_id = str(edge.get("source_id") or "").strip()
        target_id = str(edge.get("target_id") or "").strip()
        rel_type = _to_lower(edge.get("relationship_type"))
        if source_id and target_id and rel_type:
            normalized_edges.append(
                {
                    "source_id": source_id,
                    "target_id": target_id,
                    "relationship_type": rel_type,
                }
            )

    return node_by_id, normalized_edges


def _company_locations(node_by_id: dict[str, dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, set[str]]:
    locations: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if edge["relationship_type"] != "located_in":
            continue

        company = node_by_id.get(edge["source_id"], {})
        location = node_by_id.get(edge["target_id"], {})
        if _to_lower(company.get("entity_type")) != "company":
            continue
        if _to_lower(location.get("entity_type")) != "location":
            continue

        company_id = str(company.get("id"))
        location_value = str(location.get("value") or "").strip().lower()
        if company_id and location_value:
            locations[company_id].add(location_value)

    return locations


def _company_contacts(
    node_by_id: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    company_phones: dict[str, list[str]] = defaultdict(list)
    company_people: dict[str, list[str]] = defaultdict(list)

    for edge in edges:
        rel_type = edge["relationship_type"]
        source = node_by_id.get(edge["source_id"], {})
        target = node_by_id.get(edge["target_id"], {})

        if _to_lower(source.get("entity_type")) != "company":
            continue
        company_id = str(source.get("id") or "")
        if not company_id:
            continue

        if rel_type == "contact_phone" and _to_lower(target.get("entity_type")) == "phone":
            value = str(target.get("value") or "").strip()
            if value:
                company_phones[company_id].append(value)

        if rel_type in {"hr_contact", "contact_person"} and _to_lower(target.get("entity_type")) in {
            "person",
            "agent",
        }:
            value = str(target.get("value") or "").strip()
            if value:
                company_people[company_id].append(value)

    return company_phones, company_people


def _company_roles_and_licenses(
    node_by_id: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    company_roles: dict[str, set[str]] = defaultdict(set)
    company_licenses: dict[str, set[str]] = defaultdict(set)

    role_relationships = {"has_role", "role", "offers_role", "job_role"}
    license_relationships = {"has_license", "license", "licensed_as", "license_number"}

    for edge in edges:
        source = node_by_id.get(edge["source_id"], {})
        target = node_by_id.get(edge["target_id"], {})
        if _to_lower(source.get("entity_type")) != "company":
            continue

        company_id = str(source.get("id") or "")
        rel_type = edge["relationship_type"]
        target_type = _to_lower(target.get("entity_type"))
        target_value = str(target.get("value") or "").strip().lower()
        if not company_id or not target_value:
            continue

        if rel_type in role_relationships or target_type == "role":
            company_roles[company_id].add(target_value)

        if rel_type in license_relationships or target_type in {"license", "license_number"}:
            company_licenses[company_id].add(target_value)

    return company_roles, company_licenses


def _phone_locations(
    node_by_id: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
    company_locations: dict[str, set[str]],
) -> dict[str, set[str]]:
    phone_to_locations: dict[str, set[str]] = defaultdict(set)

    # Direct phone -> location edges, if available.
    for edge in edges:
        source = node_by_id.get(edge["source_id"], {})
        target = node_by_id.get(edge["target_id"], {})
        if edge["relationship_type"] == "located_in":
            if _to_lower(source.get("entity_type")) == "phone" and _to_lower(target.get("entity_type")) == "location":
                phone_id = str(source.get("id") or "")
                loc_value = str(target.get("value") or "").strip().lower()
                if phone_id and loc_value:
                    phone_to_locations[phone_id].add(loc_value)

    # Inferred phone -> location via company contact_phone + company located_in.
    for edge in edges:
        if edge["relationship_type"] != "contact_phone":
            continue

        company = node_by_id.get(edge["source_id"], {})
        phone = node_by_id.get(edge["target_id"], {})
        if _to_lower(company.get("entity_type")) != "company":
            continue
        if _to_lower(phone.get("entity_type")) != "phone":
            continue

        company_id = str(company.get("id") or "")
        phone_id = str(phone.get("id") or "")
        if company_id and phone_id:
            phone_to_locations[phone_id].update(company_locations.get(company_id, set()))

    return phone_to_locations


def check_consistency(graph: dict[str, Any]) -> dict[str, Any]:
    """Compute consistency contradictions across key graph validation checks.

    Returns:
    {
      "contradictions": int,
      "checks": int,
      "consistency_score": float
    }
    consistency_score = contradictions / checks
    """
    node_by_id, edges = _build_lookup(graph)

    contradictions = 0
    checks = 0

    companies = [
        node
        for node in node_by_id.values()
        if _to_lower(node.get("entity_type")) == "company"
    ]

    company_locations = _company_locations(node_by_id, edges)
    phone_locations = _phone_locations(node_by_id, edges, company_locations)
    company_roles, company_licenses = _company_roles_and_licenses(node_by_id, edges)
    company_phones, company_people = _company_contacts(node_by_id, edges)

    # 1) company_location consistency
    for company in companies:
        company_id = str(company.get("id") or "")
        locations = company_locations.get(company_id, set())
        if not locations:
            continue
        checks += 1
        if len(locations) > 1:
            contradictions += 1

    # 2) phone_location consistency
    for phone_id, locations in phone_locations.items():
        if not locations:
            continue
        checks += 1
        if len(locations) > 1:
            contradictions += 1

    # 3) company_role_license consistency
    for company in companies:
        company_id = str(company.get("id") or "")
        roles = company_roles.get(company_id, set())
        licenses = company_licenses.get(company_id, set())
        if not roles:
            continue
        checks += 1
        if not licenses or len(licenses) > 1:
            contradictions += 1

    # 4) company_contact_validation
    for company in companies:
        company_id = str(company.get("id") or "")
        phones = company_phones.get(company_id, [])
        people = company_people.get(company_id, [])

        checks += 1
        has_valid_phone = any(_is_valid_phone(phone) for phone in phones)
        has_named_contact = any(str(person).strip() for person in people)
        if not has_valid_phone and not has_named_contact:
            contradictions += 1

    return {
        "contradictions": contradictions,
        "checks": checks,
        "consistency_score": _safe_float(contradictions, checks),
    }


def run_full_consistency_check(entities: dict[str, Any], graph: dict[str, Any]) -> dict[str, Any]:
    """
    Merge graph-structure consistency with DB-backed cross-reference checks.
    """
    graph_result = check_consistency(graph or {"nodes": [], "edges": []})
    try:
        db_result = check_entity_consistency_against_db(entities or {})
    except Exception:
        db_result = {
            "db_contradictions": 0,
            "db_checks_run": 0,
            "contradiction_details": [],
            "company_found_in_registry": False,
            "company_is_blacklisted": False,
            "typosquatting_suspected": False,
            "typosquatting_target": None,
        }

    total_contradictions = int(graph_result.get("contradictions") or 0) + int(db_result.get("db_contradictions") or 0)
    total_checks = int(graph_result.get("checks") or 0) + int(db_result.get("db_checks_run") or 0)

    return {
        "contradictions": total_contradictions,
        "checks": total_checks,
        "consistency_score": _safe_float(total_contradictions, total_checks),
        "graph_contradictions": graph_result.get("contradictions", 0),
        "graph_checks": graph_result.get("checks", 0),
        "db_contradictions": db_result.get("db_contradictions", 0),
        "db_checks_run": db_result.get("db_checks_run", 0),
        "contradiction_details": db_result.get("contradiction_details", []),
        "company_found_in_registry": db_result.get("company_found_in_registry", False),
        "company_is_blacklisted": db_result.get("company_is_blacklisted", False),
        "typosquatting_suspected": db_result.get("typosquatting_suspected", False),
        "typosquatting_target": db_result.get("typosquatting_target"),
    }
