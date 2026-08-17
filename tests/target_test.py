#!/usr/bin/env python3
"""Offline unit checks for target keying: the worker pack is model/quant/settings sensitive.

No server or model needed. Proves resolve_artifacts keys the pack by the FULL target, so a
different quant or serving setting routes to a different pack / grade instead of silently
reusing the wrong one, while settings order does not matter. Exit 0 on PASS.
"""
import os, sys, copy
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from opencode_worker import DEFAULT_TARGET, DEFAULT_SETTINGS, resolve_artifacts

base = resolve_artifacts(DEFAULT_TARGET)

# quant is part of the key and the pack dir
t = copy.deepcopy(DEFAULT_TARGET); t["quant"] = "Q4_K_M"
assert resolve_artifacts(t)["key"] != base["key"], "quant must change the key"
assert resolve_artifacts(t)["pack_dir"] != base["pack_dir"], "quant must change the pack dir"

# settings are part of the key
t = copy.deepcopy(DEFAULT_TARGET); t["settings"] = {"context": 262144, "thinking": False}
assert resolve_artifacts(t)["key"] != base["key"], "settings must change the key"
assert resolve_artifacts(t)["settings_sig"] != base["settings_sig"], "settings sig must differ"

# settings signature is order-stable: the SAME settings in reversed insertion order key the same
t = copy.deepcopy(DEFAULT_TARGET)
t["settings"] = dict(reversed(list(DEFAULT_TARGET["settings"].items())))
assert resolve_artifacts(t)["key"] == base["key"], "settings sig must be order-stable"

# the CLI/MCP-shaped target resolves to the same key as DEFAULT_TARGET
cli = {"model": {"providerID": "mainframe-qwen38", "id": "qwen3.8-27b"}, "quant": "Q8_0",
       "harness": "opencode", "settings": DEFAULT_SETTINGS, "env": None}
assert resolve_artifacts(cli)["key"] == base["key"], "CLI-shaped target must match default key"

# the agent name is target-agnostic (one fixed install path); the pack around it is not
assert resolve_artifacts(t)["agent"] == base["agent"] == "opencode-worker"
assert base["pack_agent"].startswith(base["pack_dir"])
assert base["agent_file"] == ".opencode/agent/opencode-worker.md"

print("PASS: target keying is model/quant/settings sensitive and order-stable")
