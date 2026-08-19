#!/usr/bin/env python3
"""Emit a self-contained self-building skill file from its template.

A shippable skillc skill carries EVERYTHING and fetches nothing: the carried definition, the
binds/checks, and the canonical rebuild recipe stamped in VERBATIM. The template
(`<name>.skill.md.in`) holds the authored content with a `<!-- EMIT: ... -->` placeholder where
the recipe goes; this deterministically replaces that placeholder with the body of
`seed/rebuild.skill.md` (vendored from skillc) and writes `<name>.skill.md`. Deterministic
build-time assembly only -- it never does the skill's work.

Usage: python3 scripts/emit_skill.py skills/<pack>/<name>.skill.md.in
"""
import re, sys, os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RECIPE = os.path.join(ROOT, "seed", "rebuild.skill.md")


def emit(template_path):
    tpl = open(template_path).read()
    recipe = open(RECIPE).read()
    # the recipe body = the seed minus its own YAML frontmatter (we keep the skill's frontmatter)
    body = re.sub(r"^---\n.*?\n---\n", "", recipe, count=1, flags=re.DOTALL).strip()
    stamp = ("<!-- BEGIN stamped rebuild recipe (verbatim from seed/rebuild.skill.md; the receiver "
             "runs this before the first answer) -->\n\n" + body +
             "\n\n<!-- END stamped rebuild recipe -->")
    if "<!-- EMIT:" not in tpl:
        raise SystemExit(f"no <!-- EMIT: ... --> placeholder in {template_path}")
    emitted = re.sub(r"<!-- EMIT:.*?-->", lambda _m: stamp, tpl, count=1, flags=re.DOTALL)
    # the emitted, self-contained product IS the skill's SKILL.md (the name an agent auto-loads);
    # the .in template beside it is the source. One dir = source template + shippable SKILL.md.
    out = os.path.join(os.path.dirname(template_path), "SKILL.md")
    with open(out, "w") as f:
        f.write(emitted)
    return out, len(emitted.splitlines())


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    for tpl in sys.argv[1:]:
        out, n = emit(tpl)
        print(f"emitted {os.path.relpath(out, ROOT)} ({n} lines, self-contained: recipe stamped)")
