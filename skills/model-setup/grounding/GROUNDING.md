# model-setup: grounding record

How this skill was validated. Method: clean-room ouroboros. Each rung is a FRESH `general-purpose`
agent given ONLY `skills/model-setup/SKILL.md` (told to read nothing else in the repo, no model /
quant / install hints from the prompt), operating a real bare-box GPU pod as the receiver's machine.
The skill drives; findings route back to the source; then re-ground. "built" is by execution: the
endpoint answers, auth is enforced, and a real coding function the agent wrote is executed and
asserted. Every rung was independently re-verified by the operator (auth curls + a fresh coding
probe) before its numbers entered the skill.

## Rungs (all built, all verified)

| Rung | Hardware | Model / quant | Context | tok/s | Verdict |
|---|---|---|---|---|---|
| two-card baseline | 3090 24G + A4500 20G | qwen3.8-27b Q6_K, tensor-split, MTP | 256K (37.7G/44G) | ~45 | built |
| single card | A4500 20G | qwen3.8-27b UD-Q4_K_M | 96K (19.3/20.5G) | ~29 | built + **opencode e2e passed** |
| single card | 3090 24G | qwen3.8-27b UD-Q4_K_XL | 160K (22.5/24G) | ~40 | built (97% GPU util genuine) |
| abundant / scale-up | 3090 + A4500 (44G) | qwen3.8-27b UD-Q6_K, tensor-split | 256K (33G/44G) | ~28 (~45 w/ MTP) | built; scaled UP, did not lowball |
| capture | already-served endpoint | qwen3.8-27b (quant from `/props`) | n/a | n/a | path carried; auth-verify + tuple-fill |

**The model floor held on every single run** - each cold agent, given no model hint, landed on
`unsloth/Qwen3.8-27B-GGUF` by quoting the floor policy, and none reached for the 30B-A3B MoE (the
recurring wrong answer the anchor exists to prevent). The abundant rung correctly stayed on the floor
model (no GLM/Kimi jump absent a published benchmark) and scaled the QUANT and CONTEXT up instead.

**opencode e2e (host-local 20G):** added the produced (endpoint, key) as an opencode provider,
restarted `opencode serve`, ran the driver - `opencode-worker` authenticated with the generated key
and drove a real coding task (factorial.py) to completion through the endpoint; output verified 720.
The full model-setup -> opencode handoff works with auth.

## Gaps found by grounding, folded into the source

- `--no-mmproj`: qwen3.8-27b carries a vision tower; `-hf` auto-loads CLIP and OOMs without it (the
  single most likely place a cold agent got stuck).
- Per-card quant: UD-Q4_K_M for ~20G, UD-Q4_K_XL for ~24G; `--alias` so the model id is not the gguf
  path; `-fa on` + `q8_0` KV.
- Linux CUDA reality: no Linux CUDA release binary exists (Windows-only); the official container IS
  the prebuilt Linux-CUDA path, and on a runtime-less box you extract its layers and run `llama-server`
  natively. Source build is the last resort.
- MTP speculative decoding needs `--spec-type draft-mtp --spec-draft-n-max 2` (the ~45 vs ~28 tok/s
  difference); tensor-split ratioed to card VRAM.
- Capture: how to fill quant (`/props model_path`, else `unknown`) and key-ref (the receiver's existing
  key by env-var name) for a server you did not build.
- Capability floor and mandatory generated auth were carried and honored on every rung.

## Deferred (not yet grounded)

- **AutoRound W4A16 + vLLM path.** The HF weights exist (`unsloth/Qwen3.8-27B`), so it is feasible;
  operator chose to defer it (option B) and ship the llama.cpp GGUF path first. The skill names vLLM +
  AutoRound as the throughput path but that branch has no earned numbers yet.

## Not proof, a sample

These are single-run groundings per rung, re-verified by hand. They show the file drives a cold agent
to a working, authed, capable endpoint and that the model floor holds. They are evidence, not a
statistical transfer grade; raise N and add rungs to sharpen.
