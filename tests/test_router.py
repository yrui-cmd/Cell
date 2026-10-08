import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
MEMBERS = {
    "cell-brainstorm",
    "cell-plan",
    "cell-review",
    "cell-reviewer",
    "cell-manuscript-editing",
    "cell-reviewer-response",
    "cell-submission",
    "cell-visualization-code",
    "cell-data-figure",
    "cell_su7",
    "cell-cns-figure",
    "cell-ppt-edited",
}


def frontmatter_name(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"(?m)^name:\s*([^\s]+)\s*$", text)
    assert match, f"Missing name in {path}"
    return match.group(1)


def test_router_and_catalog_list_the_same_members():
    router = (SKILLS / "cell" / "SKILL.md").read_text(encoding="utf-8")
    catalog = (SKILLS / "cell" / "references" / "catalog.md").read_text(encoding="utf-8")

    table_members = {
        match.group(1)
        for line in router.splitlines()
        if line.startswith("|")
        for match in re.finditer(r"`(cell(?:[-_][a-z0-9]+)+)`", line)
    }
    catalog_members = set(re.findall(r"(?m)^- `(cell(?:[-_][a-z0-9]+)+)`$", catalog))

    assert table_members == MEMBERS
    assert catalog_members == MEMBERS


def test_member_directories_and_frontmatter_names_match():
    for name in MEMBERS:
        skill_file = SKILLS / name / "SKILL.md"
        assert skill_file.is_file(), f"Missing skill entrypoint: {name}"
        assert frontmatter_name(skill_file) == name


def test_router_frontmatter_matches_directory():
    assert frontmatter_name(SKILLS / "cell" / "SKILL.md") == "cell"
