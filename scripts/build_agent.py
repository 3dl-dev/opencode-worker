#!/usr/bin/env python3
"""Compile the worker pack for a target and install its active OpenCode agent.

The worker's system prompt is the protocol, delivered via an OpenCode *agent* (not prepended to
each task). This compiles that agent from `protocol/opencode-worker-protocol.md` (single source of
truth) into the target's worker pack under `packs/<model>__<quant>__<harness>/`, records a
manifest of the exact (model, quant, settings), and installs the active agent at
`.opencode/agent/<name>.md` (the fixed path OpenCode loads at startup - no hot reload). Re-run
after editing the protocol, then restart `opencode serve` from the repo root.

The pack is keyed by the FULL target because it is model/quant/settings sensitive: a different
model, quant, or serving setting is a different pack (and a different earned grade). v0 emits one
target (the default qwen); when a target's measured overlay lives in its own file, append it here
so the emitted prompt stays the compiled artifact for that exact target. Usage:
  python3 scripts/build_agent.py [--provider P] [--model M] [--quant Q] [--name opencode-worker]
"""
import argparse, os, sys, json

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from opencode_worker import DEFAULT_TARGET, DEFAULT_SETTINGS, resolve_artifacts  # noqa: E402


def build(provider, model, quant, name):
    target = {"model": {"providerID": provider, "id": model}, "quant": quant,
              "harness": "opencode", "settings": DEFAULT_SETTINGS, "env": None}
    art = resolve_artifacts(target)
    with open(os.path.join(ROOT, art["system_prompt"])) as f:
        protocol = f.read().strip()

    # OpenCode agent file: YAML frontmatter (config) + body (the system prompt).
    frontmatter = (
        "---\n"
        f"description: OpenCode worker under the strict worker protocol for target {art['key']} "
        f"(GENERATED from {art['system_prompt']} by scripts/build_agent.py; do not edit by hand).\n"
        "mode: primary\n"
        f"model: {provider}/{model}\n"
        "---\n"
    )
    agent_md = frontmatter + "\n" + protocol + "\n"

    # 1) pack source: packs/<slug>/agent/<name>.md + manifest.json
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

    # 2) active install: the fixed path the server loads (one target active at a time)
    active = os.path.join(ROOT, art["agent_file"])
    os.makedirs(os.path.dirname(active), exist_ok=True)
    with open(active, "w") as f:
        f.write(agent_md)
    return art, pack_agent, active


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Compile the worker pack + install its agent")
    ap.add_argument("--provider", default=DEFAULT_TARGET["model"]["providerID"])
    ap.add_argument("--model", default=DEFAULT_TARGET["model"]["id"])
    ap.add_argument("--quant", default=DEFAULT_TARGET["quant"])
    ap.add_argument("--name", default="opencode-worker")
    a = ap.parse_args()
    art, pack_agent, active = build(a.provider, a.model, a.quant, a.name)
    print(f"target {art['key']}")
    print(f"  pack   {os.path.relpath(pack_agent, ROOT)} (+ {art['pack_manifest']})")
    print(f"  active {os.path.relpath(active, ROOT)}")
    print("restart `opencode serve` from the repo root for the server to load the active agent.")
