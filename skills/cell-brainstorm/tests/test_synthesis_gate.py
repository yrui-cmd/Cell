import copy
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("synthesis_gate", ROOT / "scripts" / "synthesis_gate.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def candidate(index: int) -> dict:
    return {
        "id": f"S{index}",
        "title": f"Synthetic synthesis topic {index}",
        "question": "Which bounded judgment changes after comparable evidence is separated?",
        "relationship_to_primary_candidate": "parallel" if index == 1 else "subtopic",
        "nearest_reviews": [{
            "source_id": f"REV{index}",
            "access": "fulltext",
            "prior_synthesis": "The nearest review combines the conditions.",
            "comparison_result": "The candidate separates conditions that change the conclusion.",
        }],
        "primary_evidence": [{
            "source_id": f"PRI{index}",
            "access": "fulltext",
            "role": "Tests the load-bearing comparison.",
        }],
        "synthesis_delta": {
            "prior_synthesis": "Conditions were pooled.",
            "changed_judgment": "The conclusion is conditional rather than universal.",
            "synthesis_operation": "Compare studies by condition and endpoint.",
            "visible_artifact": "A condition-by-endpoint evidence matrix.",
            "boundaries": "Applies only to the defined population and endpoints.",
            "negating_evidence": "A prior review already performs the same comparison with the same conclusion.",
        },
        "search_status": {
            "request_succeeded": True,
            "screening_sufficient": True,
            "novelty_complete": True,
        },
        "evidence_plan": {
            "P0": "Pilot the extraction and comparison on representative studies.",
            "P1": "Complete coverage and cross-study synthesis.",
            "P2": None,
        },
        "open_items": [],
        "status": "pass",
    }


def bundle() -> dict:
    return {
        "schema_version": "synthesis-1.0",
        "run": {"as_of": "2026-10-12", "mode": "synthetic", "final_checked_at": None},
        "candidates": [candidate(index) for index in range(1, 6)],
    }


def test_valid_synthesis_contract_passes():
    assert MODULE.validate(bundle()) == []


def test_nearest_reviews_and_primary_evidence_are_distinct_required_roles():
    data = bundle()
    data["candidates"][0]["nearest_reviews"] = []
    errors = MODULE.validate(data)
    assert any("nearest_reviews" in error for error in errors)


def test_conditional_candidate_scopes_its_open_issue():
    data = bundle()
    data["candidates"][0]["status"] = "conditional"
    errors = MODULE.validate(data)
    assert any("scoped open_items" in error for error in errors)


def test_search_success_does_not_replace_novelty_completion():
    data = bundle()
    del data["candidates"][0]["search_status"]["novelty_complete"]
    errors = MODULE.validate(data)
    assert any("novelty_complete" in error for error in errors)


def test_five_unique_slots_are_required():
    data = copy.deepcopy(bundle())
    data["candidates"][4]["id"] = "S1"
    errors = MODULE.validate(data)
    assert any("unique" in error for error in errors)
