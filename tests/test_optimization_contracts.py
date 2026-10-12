import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_router_preserves_deliverable_action_authorization_and_open_claims():
    router = read("skills/cell/SKILL.md")
    handoff = read("skills/cell/references/handoff-contract.md")
    for token in ("deliverable_kind", "action_mode", "evidence_synthesis", "existing_artifact"):
        assert token in router
    for token in ("affects", "allowed_now", "fallback", "skill_snapshot"):
        assert token in handoff
    assert "用户已经明确授权的完整工作流可按依赖依次执行" in router


def test_brainstorm_has_a_separate_evidence_synthesis_contract():
    skill = read("skills/cell-brainstorm/SKILL.md")
    contract = read("skills/cell-brainstorm/references/evidence-synthesis.md")
    assert "evidence_synthesis" in skill
    assert "nearest_reviews" in contract
    assert "primary_evidence" in contract
    assert "synthesis_delta" in contract
    assert "synthesis_gate.py" in contract
    assert (SKILLS / "cell-brainstorm" / "scripts" / "synthesis_gate.py").is_file()


def test_review_templates_capture_argument_and_workflow_status():
    protocol = json.loads(read("skills/cell-review/templates/protocol.json"))
    evidence = json.loads(read("skills/cell-review/templates/evidence.json"))
    assert protocol["skill_version"] == "1.6.0"
    assert set(protocol["argument_skeleton"]) == {
        "core_answer",
        "difference_from_nearest_reviews",
        "key_comparisons",
        "competing_explanations",
        "boundaries",
    }
    assert set(evidence["workflow_status"]) == {
        "evidence_verification",
        "benchmark_execution",
        "synthesis_assessment",
        "delivery",
    }


def test_editing_and_reviewer_cover_existing_reviews_and_revision_review():
    editing = read("skills/cell-manuscript-editing/SKILL.md")
    reviewer = read("skills/cell-reviewer/SKILL.md")
    report = read("skills/cell-reviewer/references/report-and-qa.md")
    assert "已有综述稿" in editing
    assert "正面综合判断" in editing
    assert "修订复审模式" in reviewer
    for status in ("resolved", "partially_resolved", "unresolved"):
        assert status in reviewer or status in report
    for issue_type in ("field_unresolved", "manuscript_fixable", "insufficient_materials"):
        assert issue_type in report
