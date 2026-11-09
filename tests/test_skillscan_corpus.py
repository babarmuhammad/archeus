"""Loader test for the T-1080 skillscan fixture corpus (stdlib only).

Validates every tests/fixtures/skillscan/*.expected.json sidecar against its
fixture file. It never imports archeus or claude_sessions: the lint itself
arrives later with T-1079, which takes this corpus as its specification.
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent / "fixtures" / "skillscan"
RULES = {
    "hidden-unicode", "bidi-control", "instruction-override",
    "fetch-and-execute", "long-base64", "mcp-command-exec",
    "hook-command-exec", "tool-name-collision", "description-drift",
}


def test_skillscan_corpus_sidecars():
    sidecars = sorted(ROOT.glob("*.expected.json"))
    assert len(sidecars) == 36, len(sidecars)
    benign = hostile = 0
    covered = set()
    for side in sidecars:
        meta = json.loads(side.read_text(encoding="utf-8"))
        for key in ("fixture", "kind", "verdict", "findings"):
            assert key in meta, (side, key)
        fixture = ROOT / meta["fixture"]
        assert fixture.is_file(), fixture
        covered.add(meta["fixture"])
        lines = fixture.read_text(encoding="utf-8").split("\n")
        assert (meta["verdict"] == "benign") == (meta["findings"] == []), side
        benign += meta["verdict"] == "benign"
        hostile += meta["verdict"] == "hostile"
        for finding in meta["findings"]:
            assert finding["rule"] in RULES, (side, finding)
            assert isinstance(finding["line"], int), (side, finding)
            assert 1 <= finding["line"] <= len(lines), (side, finding)
            line = lines[finding["line"] - 1]
            match = finding["match"]
            if match.startswith("U+"):
                assert chr(int(match[2:], 16)) in line, (side, finding)
            else:
                assert match in line, (side, finding)
        if fixture.name.endswith((".mcp.json", ".settings.json")):
            json.loads(fixture.read_text(encoding="utf-8"))
    assert benign >= 15 and hostile >= 15, (benign, hostile)
    extra = ({p.name for p in ROOT.iterdir()} - covered
             - {s.name for s in sidecars} - {"CORPUS-NOTES.md"})
    assert not extra, extra
