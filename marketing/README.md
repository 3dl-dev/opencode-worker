# marketing

Assets for opencode-worker. Real content only.

## The message

**Local model offload for Claude Code.** Let Opus hand tasks to Qwen3.8-27B, or any other local
model, from within Claude Code: hybrid cloud and local mode for token spend optimization. The unlock
is multi-agent: wrapping one task in Opus costs more tokens than doing it yourself, but a workflow
that fans its subagent tasks out to a local worker keeps that work off your token budget. In use
there is effective parity: you delegate a subagent task the same way you would to Sonnet or Haiku,
and every result is checked by execution.

## Assets

- `unfurl.html` : 1200x630 social/OG card (open in a browser; export to PNG for the OG image).
- `promo-linkedin.mp4` : 1080x1350 (4:5). Hero, a real native session, the savings, install.
- `promo-reddit.mp4` : 1080x1920 (9:16), same sequence.

Sources:
- `scene_hero.html`, `scene_savings.html`, `scene_install.html` : the designed screens.
- `capture_cc.py` : drives the real interactive `claude` (via pexpect). It hands Claude a plain
  goal plus the offload policy, nothing about how to drive the worker, and lets the skill do the
  rest. Recorded with asciinema.
- `cc_session.cast` : that recording. It is the actual Claude Code TUI, not a mockup.

## How the videos are built

1. Terminal beat: `capture_cc.py` records a genuine Claude Code session (`cc_session.cast`), rendered
   to a gif with `agg`. Given only "build three small utilities, offload the builds to the local
   worker, verify each yourself", the skill drives everything on its own: it checks the server and
   model, confirms the worker agent, delegates each build to the Qwen worker, then independently
   re-tests every result (catching one of its own bad assertions) before reporting. Serial because
   the model is served single-slot; the token cost stays off Claude's budget either way.
2. Designed scenes: `scene_hero.html`, `scene_savings.html`, `scene_install.html` rendered to PNG at
   4:5 with a headless browser (playwright/chromium), then letterboxed onto the ink ground for 9:16
   so nothing clips.
3. Composed with `ffmpeg`: hero (5s) -> the real session -> savings (6s) -> install (9s). Social
   feeds loop it.

Everything shown is real. To re-capture with a different task, edit the goal in `capture_cc.py`.

## Runs on modest hardware

qwen3.8-27b serves on one 20 GB GPU at 96K context, 24 GB at 160K, two modest cards at 256K
(model-setup grounding, all built and verified).
