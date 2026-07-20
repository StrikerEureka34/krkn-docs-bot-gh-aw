#!/usr/bin/env python3
"""Report-only parameter drift scanner for the krkn-hub and krknctl sources.

For each documented scenario it compares the params in the source files
(env.sh, krknctl-input.json) against the committed data/params table and reports
a missing table, or missing / stale / extra params, one finding per source so the
report can link the exact file. It writes nothing to the docs.

The report renders as a rolling docs-drift issue, a checklist grouped by scenario,
with a direct file link and a suggested fix per finding. No em dashes anywhere.
Fixing is done by commenting /fix <scenario> on the issue.
"""
import argparse
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import yaml

from bot.parser import extract_env_params, extract_krknctl_params, build_skip_list

_MARKER_RE = re.compile(r'<krkn-hub-scenario\s+id="([^"]+)"')
_SOURCES = (("krkn-hub", "env.sh"), ("krknctl", "krknctl-input.json"))
_DEFAULT_HUB_URL = "https://github.com/krkn-chaos/krkn-hub/blob/main"


@dataclass
class Finding:
    scenario: str
    source: str            # "krkn-hub" | "krknctl"
    kind: str              # "missing-table" | "missing" | "stale" | "extra"
    param: str | None = None
    old: str | None = None
    new: str | None = None
    source_file: str = ""  # full krkn-hub URL
    table_file: str = ""   # website-relative path


def find_scenarios(website_root) -> list[str]:
    """Documented scenario ids from the <krkn-hub-scenario id="..."> markers."""
    root = Path(website_root) / "content/en/docs/scenarios"
    ids = set()
    for p in root.rglob("*.md"):
        ids |= set(_MARKER_RE.findall(p.read_text(encoding="utf-8")))
    return sorted(ids)


def _skip(website_root) -> set[str]:
    f = Path(website_root) / "content/en/docs/scenarios/all-scenario-env.md"
    return build_skip_list(f) if f.exists() else set()


def _source_params(scn_dir: Path, source: str, filename: str, skip: set[str]):
    """name -> ParamRecord for one source, or None if that source is absent."""
    f = scn_dir / filename
    if not f.exists():
        return None
    recs = extract_env_params(f) if source == "krkn-hub" else extract_krknctl_params(f)
    return {r.name: r for r in recs if r.name not in skip}


def _table_params(table_path: Path):
    """name -> default (str|None) from a committed data/params yaml, or None if the
    file does not exist."""
    if not table_path.exists():
        return None
    data = yaml.safe_load(table_path.read_text(encoding="utf-8")) or {}
    out = {}
    for p in data.get("params", []):
        d = p.get("default")
        out[p["name"]] = None if d is None else str(d)
    return out


def scenario_findings(scenario, krkn_hub_root, website_root, hub_url=_DEFAULT_HUB_URL):
    krkn_hub_root, website_root = Path(krkn_hub_root), Path(website_root)
    scn_dir = krkn_hub_root / scenario
    skip = _skip(website_root)
    findings = []
    for source, filename in _SOURCES:
        src = _source_params(scn_dir, source, filename, skip)
        if src is None:
            continue
        source_file = f"{hub_url}/{scenario}/{filename}"
        table_file = f"data/params/{scenario}/{source}.yaml"
        table = _table_params(website_root / table_file)
        if table is None:
            findings.append(Finding(scenario, source, "missing-table",
                new=", ".join(sorted(src)), source_file=source_file, table_file=table_file))
            continue
        for name, rec in sorted(src.items()):
            sdef = None if rec.default is None else str(rec.default)
            if name not in table:
                findings.append(Finding(scenario, source, "missing", name,
                    new=sdef, source_file=source_file, table_file=table_file))
            elif table[name] != sdef:
                findings.append(Finding(scenario, source, "stale", name,
                    old=table[name], new=sdef, source_file=source_file, table_file=table_file))
        for name in sorted(table):
            if name not in src:
                findings.append(Finding(scenario, source, "extra", name,
                    old=table[name], source_file=source_file, table_file=table_file))
    return findings


def scan(krkn_hub_root, website_root, scenarios=None, hub_url=_DEFAULT_HUB_URL):
    if scenarios is None:
        scenarios = find_scenarios(website_root)
    findings = []
    for s in scenarios:
        if (Path(krkn_hub_root) / s).is_dir():
            findings.extend(scenario_findings(s, krkn_hub_root, website_root, hub_url))
    return findings


# --- issue rendering (Option A, no em dashes) -----------------------------

def _finding_line(f: Finding) -> str:
    if f.kind == "missing-table":
        n = len(f.new.split(", ")) if f.new else 0
        return f"no {f.source} table yet, /fix will add {n} params ({f.new})"
    if f.kind == "missing":
        d = f" (default {f.new})" if f.new is not None else ""
        return f"missing from {f.source} table: {f.param}{d}"
    if f.kind == "stale":
        return f"stale in {f.source} table: {f.param} default {f.old} -> {f.new}"
    if f.kind == "extra":
        return f"extra in {f.source} table: {f.param}"
    return f.kind


def _ticked(prev_body: str) -> set[str]:
    return set(re.findall(r"- \[x\] (.+)", prev_body))


def format_report(findings, prev_body="") -> str:
    """Render Option A. Preserves a ticked checkbox for any finding line that is
    still present. Emits no em dash characters."""
    if not findings:
        return "### Docs drift report\n\nNo drift found.\n"
    ticked = _ticked(prev_body)
    by_scn = defaultdict(list)
    for f in findings:
        by_scn[f.scenario].append(f)
    n = len(by_scn)
    lines = ["### Docs drift report", "",
             f"Drift in {n} scenario{'s' if n != 1 else ''}. "
             "Tick a box when handled, or comment `/fix <scenario>` for a draft PR.", ""]
    for scn in sorted(by_scn):
        lines.append(f"<!-- drift:{scn} -->")
        lines.append(f"#### {scn}")
        for f in by_scn[scn]:
            text = _finding_line(f)
            box = "x" if text in ticked else " "
            lines.append(f"- [{box}] {text}")
            lines.append(f"  - source: {f.source_file}")
            if f.kind != "missing-table":
                lines.append(f"  - table: {f.table_file}")
            lines.append(f"  - fix: `/fix {scn}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="Scan krkn-hub for documentation drift")
    ap.add_argument("--krkn-hub", required=True, help="Path to krkn-hub repo root")
    ap.add_argument("--website", required=True, help="Path to website repo root")
    ap.add_argument("--repo", help="owner/repo to open the rolling drift issue on")
    ap.add_argument("--hub-url", default=_DEFAULT_HUB_URL, help="krkn-hub blob base URL")
    args = ap.parse_args()

    findings = scan(args.krkn_hub, args.website, hub_url=args.hub_url)

    if not args.repo:
        print(format_report(findings))
        return

    from bot.github_client import get_open_drift_body, create_or_update_drift_issue
    prev = get_open_drift_body(args.repo)
    body = format_report(findings, prev_body=prev)
    url = create_or_update_drift_issue(args.repo, "Docs drift report", body)
    print(f"Drift issue: {url}")


if __name__ == "__main__":
    main()
