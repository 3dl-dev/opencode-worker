# marketing

Assets for opencode-worker. Real content only.

## The message

**Local model offload for Claude Code.** Let Opus hand tasks to Qwen3.8-27B, or any other local
model, from within Claude Code: hybrid cloud and local mode for token spend optimization. The
mechanism is a tool-boundary worker (subscription-safe, never routes Claude's own auth), but in use
there is effective parity: you hand off a subagent task just like you would to a Sonnet or Haiku
subagent, and the only differences are that it is local and that every result is checked by execution.

## Assets

- `unfurl.html` : 1200x630 social/OG card (open in a browser; export to PNG for the OG image).
- `promo-linkedin.mp4` : 1080x1350 (4:5). Hero, then a real Claude Code session, then install.
- `promo-reddit.mp4` : 1080x1920 (9:16), same sequence.

Sources:
- `scene_hero.html`, `scene_install.html` : the designed hero and install screens (brand type + color).
- `capture_cc.py` : drives the real interactive `claude` (via pexpect) to delegate an LRU-cache build
  to the local Qwen worker and then verify it, recorded with asciinema.
- `cc_session.cast` : that recording. It is the actual Claude Code TUI, not a mockup.

## How the videos are built

1. Terminal beat: `capture_cc.py` records a genuine Claude Code session (`cc_session.cast`), rendered
   to a gif with `agg`. It shows the real TUI: the Opus/Max banner, the `opencode-worker` delegation,
   the independent verify, and Claude's rendered results table.
2. Designed scenes: `scene_hero.html` and `scene_install.html` rendered to PNG at the target size with
   a headless browser (playwright/chromium).
3. Composed with `ffmpeg`: hero (hold 3s) -> the real session -> install (hold 6s), padded to the
   platform aspect on the ink ground. Social feeds loop it.

Everything shown is real. To re-capture with a different task, edit the prompt in `capture_cc.py` and
re-run it under asciinema.

## Runs on modest hardware

qwen3.8-27b serves on one 20 GB GPU at 96K context, 24 GB at 160K, two modest cards at 256K
(model-setup grounding, all built and verified).
