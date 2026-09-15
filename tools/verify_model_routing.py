"""Verify model routing: OmniRoute for main execution, Sonnet 5 for agents/skills."""
import json, glob, os, sys

CONFIG_PROJECTS = r"C:\Users\mab\.claude\projects\D--Claude"
SYNTHETIC = ("", "<synthetic>")


# ── Step 5 ──────────────────────────────────────────────────────────────
def is_anthropic_model(model):
    """Return True for Claude/Anthropic model ids or bare aliases."""
    m = (model or "").lower()
    if m in SYNTHETIC:
        return False
    if "claude" in m or "anthropic" in m:
        return True
    return m in ("sonnet", "opus", "haiku", "fable")


# ── Step 6 ──────────────────────────────────────────────────────────────
def is_provider_model(model):
    """Return True for non-empty, non-synthetic, non-Anthropic model ids."""
    m = model or ""
    if m in SYNTHETIC:
        return False
    return not is_anthropic_model(m)


# ── Step 7 ──────────────────────────────────────────────────────────────
def is_sonnet5(model):
    """Return True only for claude-sonnet-5 or claude-sonnet-5-* ids."""
    m = (model or "")
    return m == "claude-sonnet-5" or m.startswith("claude-sonnet-5-")


# ── Step 8 ──────────────────────────────────────────────────────────────
def load_assistant_turns(path):
    """Load all assistant-type turns from a JSONL transcript."""
    turns = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") != "assistant":
                continue
            turns.append({
                "model": (obj.get("message") or {}).get("model"),
                "sidechain": bool(obj.get("isSidechain")),
                "uuid": obj.get("uuid"),
            })
    return turns


# ── Step 9 ──────────────────────────────────────────────────────────────
def _reported(model):
    """A model id that says something about routing — None and synthetic turns
    do not."""
    return bool(model) and model not in SYNTHETIC


def check_routing(turns):
    """Check that main turns use provider models and agent turns use Sonnet 5."""
    main_violations = []
    agent_violations = []

    for t in turns:
        model = t["model"]
        if t["sidechain"]:
            # Agent/skill turn — must be Sonnet 5
            if _reported(model) and not is_sonnet5(model):
                agent_violations.append(t)
        else:
            # Main execution turn — must be provider (non-Anthropic)
            if _reported(model) and not is_provider_model(model):
                main_violations.append(t)

    main_models = sorted({t["model"] for t in turns
                          if not t["sidechain"] and _reported(t["model"])})
    agent_models = sorted({t["model"] for t in turns
                           if t["sidechain"] and _reported(t["model"])})

    return {
        "main_models": main_models,
        "agent_models": agent_models,
        "main_violations": main_violations,
        "agent_violations": agent_violations,
    }


# ── Step 10 ─────────────────────────────────────────────────────────────
def newest_transcript():
    """Find the newest .jsonl transcript in the config projects dir."""
    files = glob.glob(os.path.join(CONFIG_PROJECTS, "*.jsonl"))
    if not files:
        sys.exit("ERROR: no transcript found in " + CONFIG_PROJECTS)
    return max(files, key=os.path.getmtime)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else newest_transcript()

    turns = load_assistant_turns(path)
    result = check_routing(turns)

    print("TRANSCRIPT:", path)
    print("MAIN MODELS:", result["main_models"])
    print("AGENT/SKILL MODELS:", result["agent_models"])
    print("MAIN VIOLATIONS:", len(result["main_violations"]))
    print("AGENT/SKILL VIOLATIONS:", len(result["agent_violations"]))

    for t in result["main_violations"]:
        print("  - [main] %s (uuid=%s)" % (t["model"], t["uuid"]))
    for t in result["agent_violations"]:
        print("  - [agent] %s (uuid=%s)" % (t["model"], t["uuid"]))

    failed = bool(result["main_violations"] or result["agent_violations"])
    print("RESULT:", "FAIL" if failed else "PASS")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
