#!/usr/bin/env python3
"""Compile the worker pack for a target and install it as the active OpenCode worker.

Capturing an OpenCode worker is two-sided: a Claude-side orchestrator skill (target-agnostic) and
an opencode-side worker pack that is model/quant/settings sensitive. This builds the pack and
installs it. The pack holds, keyed by the FULL target under
`packs/<model>__<quant>__<harness>/`:
  - agent/<name>.md   the system prompt (protocol, compiled from protocol/...) PLUS the target's
                      settings rendered into frontmatter: our-side permission gating and sampling;
  - manifest.json     the exact model/quant/settings + resolve key;
  - skills/           OpenCode skills the worker itself loads (added by measured divergence).

Install lays the pack into the fixed paths OpenCode loads at server STARTUP (no hot reload):
`.opencode/agent/<name>.md` and `.opencode/skills/`. Only one target is active at a time; the
active target is recorded in `.opencode/active-target.json`. Re-run after editing the protocol or
settings, then restart `opencode serve` from the repo root. Usage:
  python3 scripts/build_agent.py [--provider P] [--model M] [--quant Q] [--name opencode-worker]
  python3 scripts/build_agent.py --list        # show available packs and the active one
"""
import argparse, os, sys, json, shutil

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from opencode_worker import DEFAULT_TARGET, DEFAULT_SETTINGS, resolve_artifacts  # noqa: E402


def _yaml_frontmatter(desc, provider, model, settings):
    """Minimal YAML frontmatter: agent config. Renders our-side permission gating and sampling
    from the target settings so gating is explicit and target-keyed, not a server default."""
    lines = ["---", f"description: {desc}", "mode: primary", f"model: {provider}/{model}"]
    for k in ("temperature", "top_p"):
        if isinstance(settings.get(k), (int, float)):
            lines.append(f"{k}: {settings[k]}")
    perm = settings.get("permission") or {}
    if perm:
        lines.append("permission:")
        for tool, action in perm.items():
            lines.append(f"  {tool}: {action}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def build(provider, model, quant, name):
    target = {"model": {"providerID": provider, "id": model}, "quant": quant,
              "harness": "opencode", "settings": DEFAULT_SETTINGS, "env": None}
    art = resolve_artifacts(target)
    with open(os.path.join(ROOT, art["system_prompt"])) as f:
        protocol = f.read().strip()

    desc = (f"OpenCode worker under the strict worker protocol for target {art['key']} "
            f"(GENERATED from {art['system_prompt']} by scripts/build_agent.py; do not edit by hand).")
    agent_md = _yaml_frontmatter(desc, provider, model, target["settings"]) + "\n" + protocol + "\n"

    # 1) pack source: packs/<slug>/{agent/<name>.md, manifest.json}
    pack_dir = os.path.join(ROOT, art["pack_dir"])
    pack_agent = os.path.join(ROOT, art["pack_agent"])
    os.makedirs(os.path.dirname(pack_agent), exist_ok=True)
    with open(pack_agent, "w") as f:
        f.write(agent_md)
    manifest = {
        "key": art["key"], "agent": name,
        "model": target["model"], "quant": quant, "settings": target["settings"],
        "harness": target["harness"], "env": target["env"],
        "system_prompt": art["system_prompt"], "deltas": art["deltas"], "version": art["version"],
    }
    with open(os.path.join(ROOT, art["pack_manifest"]), "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")

    # 2) active install: fixed paths the server loads (one target active at a time)
    active = os.path.join(ROOT, art["agent_file"])
    os.makedirs(os.path.dirname(active), exist_ok=True)
    with open(active, "w") as f:
        f.write(agent_md)
    # the pack's OpenCode skill-pack (if any) installs to .opencode/skills/
    pack_skills = os.path.join(pack_dir, "skills")
    active_skills = os.path.join(ROOT, ".opencode", "skills")
    installed_skills = []
    if os.path.isdir(pack_skills):
        for entry in sorted(os.listdir(pack_skills)):
            src, dst = os.path.join(pack_skills, entry), os.path.join(active_skills, entry)
            if os.path.isdir(src):
                shutil.rmtree(dst, ignore_errors=True)
                shutil.copytree(src, dst)
                installed_skills.append(entry)
    with open(os.path.join(ROOT, ".opencode", "active-target.json"), "w") as f:
        json.dump({"key": art["key"], "agent": name, "pack_dir": art["pack_dir"],
                   "model": target["model"], "quant": quant, "settings": target["settings"],
                   "skills": installed_skills}, f, indent=2)
        f.write("\n")
    return art, pack_agent, active, installed_skills


def list_packs():
    packs_root = os.path.join(ROOT, "packs")
    active_path = os.path.join(ROOT, ".opencode", "active-target.json")
    active_key = None
    if os.path.exists(active_path):
        active_key = json.load(open(active_path)).get("key")
    print(f"active: {active_key or '(none installed)'}")
    if not os.path.isdir(packs_root):
        print("packs: (none built)"); return
    for slug in sorted(os.listdir(packs_root)):
        man = os.path.join(packs_root, slug, "manifest.json")
        key = json.load(open(man)).get("key") if os.path.exists(man) else "(no manifest)"
        mark = " *" if key == active_key else ""
        print(f"  {slug}{mark}  {key}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Compile the worker pack + install its agent")
    ap.add_argument("--provider", default=DEFAULT_TARGET["model"]["providerID"])
    ap.add_argument("--model", default=DEFAULT_TARGET["model"]["id"])
    ap.add_argument("--quant", default=DEFAULT_TARGET["quant"])
    ap.add_argument("--name", default="opencode-worker")
    ap.add_argument("--list", action="store_true", help="show available packs and the active one")
    a = ap.parse_args()
    if a.list:
        list_packs(); sys.exit(0)
    art, pack_agent, active, skills = build(a.provider, a.model, a.quant, a.name)
    print(f"target {art['key']}")
    print(f"  pack     {os.path.relpath(pack_agent, ROOT)} (+ {art['pack_manifest']})")
    print(f"  active   {os.path.relpath(active, ROOT)}  skills={skills or '[]'}")
    print("restart `opencode serve` from the repo root for the server to load the active agent.")
