"""Compare the published krkn-hub tab tables against what the bot would generate.

Mirrors the analysis in krkn-chaos/krkn-hub#363, but for the krkn-hub tab rather
than the krknctl one. #363 compared krknctl flags against the published krknctl
table. The krkn-hub tab is a separately curated set of descriptions that has no
home in any source file, so it is not covered there.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

WEBSITE = Path(r"C:\Users\nayus\Desktop\LFX\krkn_Sync\website")
HUB = Path(r"C:\Users\nayus\Desktop\LFX\krkn_Sync\krkn-hub")
KRKN = Path(r"C:\Users\nayus\Desktop\LFX\krkn_Sync\krkn")
BOT = Path(r"C:\Users\nayus\Desktop\LFX\krkn_Sync\krkn-docs-bot-gh-aw\krkn-docs-bot-gh-aw")


def published_rows(scenario):
    """{param: (description, type, default)} from the hand-written table on main."""
    rel = f"content/en/docs/scenarios/{scenario}/_tab-krkn-hub.md"
    try:
        text = subprocess.run(["git", "show", f"main:{rel}"], cwd=WEBSITE,
                              capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError:
        return {}
    rows = {}
    for line in text.splitlines():
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        name = cells[0].strip("`")
        # Skip the header and the ---- separator
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
            continue
        rows[name] = (cells[1], cells[2] if len(cells) > 2 else "",
                      cells[3] if len(cells) > 3 else "")
    return rows


def generated_rows(scenario, out):
    """{param: description} the bot would emit for the krkn-hub source."""
    env = {"KRKN_HUB_PATH": str(HUB), "KRKN_PATH": str(KRKN),
           "WEBSITE_ROOT": str(out), "PYTHONPATH": str(BOT),
           "PATH": __import__("os").environ["PATH"],
           "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")}
    subprocess.run([sys.executable, "-m", "bot.doc_bot", "--scenario", scenario],
                   env=env, capture_output=True)
    f = out / "data" / "params" / scenario / "krkn-hub.yaml"
    if not f.exists():
        return {}
    return {r["name"]: r.get("description", "")
            for r in yaml.safe_load(f.read_text(encoding="utf-8"))["params"]}


blank, changed, typed, ok = [], [], 0, 0
with tempfile.TemporaryDirectory() as td:
    out = Path(td)
    for d in sorted(HUB.glob("*/env.sh")):
        scenario = d.parent.name
        pub = published_rows(scenario)
        if not pub:
            continue
        gen = generated_rows(scenario, out)
        for name, (desc, typ, _default) in pub.items():
            if name not in gen:
                continue
            if typ:
                typed += 1
            g = gen[name]
            if not g:
                blank.append((scenario, name, desc))
            elif g.strip() != desc.strip():
                changed.append((scenario, name, desc, g))
            else:
                ok += 1

print(f"identical            : {ok}")
print(f"published -> BLANK   : {len(blank)}")
print(f"published -> changed : {len(changed)}")
print(f"rows with a Type cell: {typed}")

print("\n===== would go BLANK (no krknctl entry, no env.sh comment) =====")
for s, n, d in blank:
    print(f"  {s} / {n}\n      published: {d[:110]}")

print("\n===== would CHANGE (krknctl description replaces the curated one) =====")
for s, n, d, g in changed[:40]:
    print(f"  {s} / {n}\n      published: {d[:110]}\n      generated: {g[:110]}")
if len(changed) > 40:
    print(f"  ... {len(changed)-40} more")
