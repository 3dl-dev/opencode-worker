# marketing

Assets for opencode-worker. Real content only, no fabricated demos.

## The message

**Local model offload for Claude Code.** Let Opus hand tasks to Qwen3.8-27B, or any other local
model, from within Claude Code: hybrid cloud and local mode for token spend optimization. The
mechanism is a tool-boundary worker (subscription-safe, never routes Claude's own auth), but in use
there is **effective parity**: you hand off a subagent task just like you would to a Sonnet or Haiku
subagent, and the only differences are that it is local and that every result is checked by execution.

## The demo: record the real thing (do not hand-draw it)

A rendered terminal is a fabrication and reads as one. The authentic "this is Claude Code" clip is a
**screen recording of the real TUI**, which has to be captured on a real screen (it cannot be
screen-captured from inside a tool call). To make it:

1. Serve Qwen (repo `model-setup`) and start `opencode serve` from the repo root so the worker agent
   loads.
2. In a real Claude Code session with `opencode-worker` installed, give Opus a normal coding task and
   let it delegate the implementation to the local Qwen worker (it hands off like a subagent). A good
   meaty task: "build an LRU cache with an O(1) get/put and a test suite, delegate the build to the
   local qwen worker, then verify it yourself."
3. Screen-record the terminal, ~30 to 60 seconds. That footage is the demo, for both LinkedIn (native
   aspect) and Reddit (crop to square if you like).

That a real run of this works is not hypothetical: `claude_events.jsonl` here is the raw event log of
exactly that session (Claude Code delegated an LRU-cache build to the Qwen worker via the
`opencode-worker` MCP, then read both files and ran the tests to verify: "Built, verified
independently").

## Runs on modest hardware

qwen3.8-27b serves on one 20 GB GPU at 96K context, 24 GB at 160K, two modest cards at 256K
(model-setup grounding, all built and verified).

## Files

- `unfurl.html`: 1200x630 social card. Open in a browser and export to PNG for the OG image. (Authored
  as source; eyeball it before use.)
- `claude_events.jsonl`: raw event log of the real delegation session (proof, and raw material if you
  want to build a faithful capture).
- `README.md`: this file.
