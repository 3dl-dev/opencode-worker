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
- `promo-linkedin.mp4` : 1080x1350 (4:5). Hero, a real multi-agent session, the savings, install.
- `promo-reddit.mp4` : 1080x1920 (9:16), same sequence.

Sources:
- `scene_hero.html`, `scene_savings.html`, `scene_install.html` : the designed screens.
- `capture_cc.py` : drives the real interactive `claude` (via pexpect) to fan three subagent tasks
  out to the local Qwen worker (one delegation each), then verify each. Recorded with asciinema.
- `cc_session.cast` : that recording. It is the actual Claude Code TUI, not a mockup.

## How the videos are built

1. Terminal beat: `capture_cc.py` records a genuine Claude Code session (`cc_session.cast`), rendered
   to a gif with `agg`. You see the real TUI: the Opus/Max banner, three `Called opencode-worker`
   delegations serialized because Qwen is single-slot, Opus verifying each, and the results table.
2. Designed scenes: `scene_hero.html`, `scene_savings.html`, `scene_install.html` rendered to PNG at
   the target size with a headless browser (playwright/chromium).
3. Composed with `ffmpeg`: hero (3s) -> the real session -> savings (4s) -> install (6s), padded to
   the platform aspect on the ink ground. Social feeds loop it.

Everything shown is real. To re-capture with different tasks, edit the prompt in `capture_cc.py`.

## Runs on modest hardware

qwen3.8-27b serves on one 20 GB GPU at 96K context, 24 GB at 160K, two modest cards at 256K
(model-setup grounding, all built and verified).
