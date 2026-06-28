#!/usr/bin/env python3
import argparse
import json
import yaml
from datetime import date
from pathlib import Path

from bot.parser import extract_env_params, extract_krknctl_params, build_skip_list
from bot.github_client import create_or_update_drift_issue


def _env_defaults(path: Path) -> dict[str, str]:
    return {r.name: (r.default if r.default is not None else "")
            for r in extract_env_params(path)}


def _krknctl_defaults(path: Path) -> dict[str, str]:
    return {r.name: (r.default if r.default is not None else "")
            for r in extract_krknctl_params(path)}


def _yaml_defaults(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    result = {}
    for p in data.get("params", []):
        v = p.get("default")
        result[p["name"]] = str(v) if v is not None else ""
    return result


def _source_defaults(scenario_dir: Path) -> dict[str, str]:
    params: dict[str, str] = {}
    env_sh = scenario_dir / "env.sh"
    krknctl_json = scenario_dir / "krknctl-input.json"
    if env_sh.exists():
        params.update(_env_defaults(env_sh))
    if krknctl_json.exists():
        params.update(_krknctl_defaults(krknctl_json))
    return params


def _doc_defaults(scenario_name: str, website_root: Path) -> dict[str, str]:
    base = website_root / "data" / "params" / scenario_name
    params: dict[str, str] = {}
    for source in ("krkn-hub", "krknctl"):
        params.update(_yaml_defaults(base / f"{source}.yaml"))
    return params


def find_drift(
    krkn_hub_root: Path,
    website_root: Path,
    skip: set[str],
) -> dict[str, dict]:
    """Returns {scenario: {missing, stale, extra}} for all scenarios with drift."""
    results = {}

    for scenario_dir in krkn_hub_root.iterdir():
        if not scenario_dir.is_dir():
            continue

        source_params = {k: v for k, v in _source_defaults(scenario_dir).items()
                         if k not in skip}
        if not source_params:
            continue

        doc_params = _doc_defaults(scenario_dir.name, website_root)

        source_keys = set(source_params.keys())
        doc_keys = set(doc_params.keys())
        missing = sorted(source_keys - doc_keys)
        extra = sorted(doc_keys - source_keys)
        stale = sorted(
            k for k in source_keys & doc_keys if source_params[k] != doc_params[k]
        )

        if missing or extra or stale:
            results[scenario_dir.name] = {"missing": missing, "extra": extra, "stale": stale}

    return results


def format_drift_report(drift: dict[str, dict], scan_date: str) -> tuple[str, str]:
    """Returns (issue_title, issue_body) for the GitHub drift issue."""
    title = f"docs: documentation drift report - {scan_date}"
    lines = [
        "## Documentation Drift Report",
        "",
        f"Scan date: {scan_date}  ",
        f"Scenarios with drift: **{len(drift)}**",
        "",
        "---",
        "",
    ]
    for scenario, info in sorted(drift.items()):
        lines.append(f"### `{scenario}`")
        lines.append("")
        if info["missing"]:
            lines.append("**Missing from docs** (in source, not in data file):")
            for p in info["missing"]:
                lines.append(f"- `{p}`")
            lines.append("")
        if info["stale"]:
            lines.append("**Stale defaults** (default value changed in source):")
            for p in info["stale"]:
                lines.append(f"- `{p}`")
            lines.append("")
        if info["extra"]:
            lines.append("**Extra in docs** (documented param removed from source):")
            for p in info["extra"]:
                lines.append(f"- `{p}`")
            lines.append("")
        lines.append(f"> To auto-fix: reply `@krkn-docs-bot /fix {scenario}` on this issue")
        lines.append("")
    return title, "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan krkn-hub for documentation drift")
    parser.add_argument("--krkn-hub", required=True, help="Path to krkn-hub repo root")
    parser.add_argument("--website", required=True, help="Path to website repo root")
    parser.add_argument("--repo", help="GitHub repo (owner/repo) to open drift issue on")
    parser.add_argument("--output", help="Write drift JSON report to this file path")
    args = parser.parse_args()

    krkn_hub = Path(args.krkn_hub)
    website = Path(args.website)
    all_env_md = website / "content/en/docs/scenarios/all-scenario-env.md"

    skip = build_skip_list(all_env_md)
    drift = find_drift(krkn_hub, website, skip)

    if args.output:
        Path(args.output).write_text(json.dumps(drift, indent=2))
        print(f"Drift report written to {args.output}")

    if drift:
        print(f"\nFound drift in {len(drift)} scenario(s):")
        for scenario, info in sorted(drift.items()):
            print(f"  {scenario}:")
            if info["missing"]:
                print(f"    missing: {info['missing']}")
            if info["stale"]:
                print(f"    stale:   {info['stale']}")
            if info["extra"]:
                print(f"    extra:   {info['extra']}")
    else:
        print("No drift found. All scenarios are up to date.")

    if args.repo and drift:
        scan_date = date.today().isoformat()
        title, body = format_drift_report(drift, scan_date)
        url = create_or_update_drift_issue(args.repo, title, body)
        print(f"\nDrift issue: {url}")


if __name__ == "__main__":
    main()
