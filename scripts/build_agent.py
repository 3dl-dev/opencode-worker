#!/usr/bin/env python3
"""Compile the worker's OpenCode agent config from the protocol (single source of truth).

The worker's system prompt is the protocol, delivered via an OpenCode *agent* rather than
prepended to each task. OpenCode loads agents from `.opencode/agent/<name>.md` at server
startup (no hot reload), so this writes that file from `protocol/opencode-worker-protocol.md`.
Re-run after editing the protocol, then restart `opencode serve`.

The agent name and target are parameters: the protocol already folds in target #1's measured
`qwen-opencode` overlay, so v0 emits one agent for the default (qwen) target. When a target's
overlay lives in its own file, append it here, keyed by target, so the emitted prompt stays the
compiled artifact for that exact (model, harness). Usage:
  python3 scripts/build_agent.py [--provider P] [--model M] [--name opencode-worker]
"""
import argparse, os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROTOCOL = os.path.join(ROOT, "protocol", "opencode-worker-protocol.md")


def build(provider, model, name):
    with open(PROTOCOL) as f:
        protocol = f.read().strip()
    # OpenCode agent file: YAML frontmatter (config) + body (the system prompt).
    frontmatter = (
        "---\n"
        f"description: OpenCode worker under the strict worker protocol (GENERATED from "
        f"protocol/opencode-worker-protocol.md by scripts/build_agent.py; do not edit by hand).\n"
        "mode: primary\n"
        f"model: {provider}/{model}\n"
        "---\n"
    )
    out_dir = os.path.join(ROOT, ".opencode", "agent")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{name}.md")
    with open(out, "w") as f:
        f.write(frontmatter + "\n" + protocol + "\n")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Compile the worker agent config from the protocol")
    ap.add_argument("--provider", default="mainframe-qwen38")
    ap.add_argument("--model", default="qwen3.8-27b")
    ap.add_argument("--name", default="opencode-worker")
    a = ap.parse_args()
    path = build(a.provider, a.model, a.name)
    print(f"wrote {os.path.relpath(path, ROOT)} (agent '{a.name}', target {a.provider}/{a.model})")
    print("restart `opencode serve` from the repo root for the server to load it.")
