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
- `promo-linkedin.mp4` : 1080x1350 (4:5) promo. Hero, then the real delegation, then install.
- `promo-reddit.mp4` : 1080x1920 (9:16) promo, same sequence.

Sources they are built from:
- `scene_hero.html`, `scene_install.html` : the designed hero and install screens (brand type + color).
- `claude_events.jsonl` : raw event log of a real Claude Code session that delegated an LRU-cache build
  to a local Qwen worker and then verified it (read both files, ran the tests).
- `render_claude.py` : renders that event log into the terminal beat. `demo.gif` is its output.

## How the videos are built (reproducible)

1. Terminal beat, from the real events: `python3 render_claude.py <wrap-width>` recorded with
   `asciinema`, rendered to a gif with `agg`.
2. Designed scenes: `scene_hero.html` and `scene_install.html` rendered to PNG at the target size with
   a headless browser (playwright/chromium).
3. Composed with `ffmpeg`: hero (hold 3s) -> terminal capture -> install (hold 3s), padded to the
   platform aspect on the ink ground. Social feeds loop it.

The terminal beat is a rendering of a real captured session, not a hand-typed mockup. The truest
"this is Claude Code" clip is still a screen recording of the live TUI, which has to be captured on a
real screen; these promos are the designed, shareable version.

## Runs on modest hardware

qwen3.8-27b serves on one 20 GB GPU at 96K context, 24 GB at 160K, two modest cards at 256K
(model-setup grounding, all built and verified).
