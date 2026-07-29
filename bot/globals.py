#!/usr/bin/env python3
"""Generate the two global parameter pages from their sources.

krknctl globals come from krkn/containers/krknctl-input.json, which carries a
"group" field and is displayed by CLI flag name. krkn-hub globals come from
krkn-hub/env.sh, which has no grouping of its own: it borrows one by joining
each export name against the krknctl "variable" field. Exports that do not join
land in a single "other" group.

Section headings and their order live in the website page, not here. The page
writes its own heading and then calls the shortcode for that group.
"""
import argparse
from collections import defaultdict
from pathlib import Path

from bot.parser import extract_env_params, extract_krknctl_params
from bot.emitter import emit_data_file, load_descriptions
from bot.descriptions import resolve_descriptions

GLOBAL_SCENARIO = "globals"
OTHER_GROUP = "other"
_KRKNCTL_REL = "containers/krknctl-input.json"


def build_groups(krkn_hub_root, krkn_root):
    """(krknctl_records, env_records), both with .group populated.

    krknctl records are keyed on the CLI flag because that is what its page
    displays. env records keep the variable name and borrow the group, and a
    description, from the matching krknctl entry when they have none of their own."""
    ctl_path = Path(krkn_root) / _KRKNCTL_REL
    by_flag = extract_krknctl_params(ctl_path, key="name")
    by_var = {r.name: r for r in extract_krknctl_params(ctl_path)}

    env_path = Path(krkn_hub_root) / "env.sh"
    env = extract_env_params(env_path) if env_path.exists() else []
    for r in env:
        match = by_var.get(r.name)
        r.group = match.group if match and match.group else OTHER_GROUP
        # An inline comment in env.sh is krkn-hub's own wording, so it wins.
        if not r.description and match and match.description:
            r.description = match.description
            r.description_source = "krknctl"
    return by_flag, env


def _by_group(records):
    out = defaultdict(list)
    for r in records:
        out[r.group or OTHER_GROUP].append(r)
    return out


def _no_descriptions(scenario, names):
    """Globals take their wording from the sources or from the existing file. The
    gh-aw agent fills any residue, same as the per-scenario path."""
    return {}


def emit(website_root, krkn_hub_root, krkn_root, source_ref="HEAD"):
    """Write data/params/globals/<source>.yaml, one file per source. Returns the
    paths written.

    Every param carries its group, and the page's shortcode filters on it. Keeping
    the grouping in the data rather than in filenames means a new upstream group
    costs no new file. Existing descriptions win, so hand-edited wording on the
    page survives regeneration."""
    ctl, env = build_groups(krkn_hub_root, krkn_root)
    written = []
    for source, records in (("krknctl", ctl), ("krkn-hub", env)):
        # Group order is stable so regenerating twice is byte identical.
        ordered = [r for _, rs in sorted(_by_group(records).items()) for r in rs]
        existing = load_descriptions(
            Path(website_root) / "data/params" / GLOBAL_SCENARIO / f"{source}.yaml")
        descs, _ = resolve_descriptions(GLOBAL_SCENARIO, ordered, existing, _no_descriptions)
        written.append(
            emit_data_file(website_root, GLOBAL_SCENARIO, source, ordered, descs, source_ref))
    return written


_PAGES = (
    ("krknctl", "content/en/docs/scenarios/all-scenario-env-krknctl.md"),
    ("krkn-hub", "content/en/docs/scenarios/all-scenario-env.md"),
)


def scaffold(website_root, krkn_hub_root, krkn_root):
    """Replace the hand-written tables on the two global pages with group-filtered
    param-table calls. Returns a report line per table.

    The group is derived from each table's own rows, so no marker or heading map is
    needed. A table whose rows span groups, or whose group is claimed by another
    table on the same page, is left alone rather than guessed at."""
    from bot.scaffold import inject_global_shortcodes

    ctl, env = build_groups(krkn_hub_root, krkn_root)
    by_source = {"krknctl": ctl, "krkn-hub": env}
    report = []
    for source, rel in _PAGES:
        page = Path(website_root) / rel
        if not page.exists():
            continue
        text = page.read_text(encoding="utf-8")
        out, lines = inject_global_shortcodes(
            text, source, {r.name: r.group for r in by_source[source]})
        if out != text:
            page.write_text(out, encoding="utf-8")
        report += [f"{Path(rel).name}: {line}" for line in lines]
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate global parameter data files")
    ap.add_argument("--krkn-hub", required=True, help="Path to the krkn-hub repo root")
    ap.add_argument("--krkn", required=True, help="Path to the krkn repo root")
    ap.add_argument("--website", default=".", help="Path to the website repo root")
    ap.add_argument("--source-ref", default="HEAD")
    ap.add_argument("--scaffold", action="store_true",
                    help="Also replace the tables on the two global pages with "
                         "param-table calls")
    args = ap.parse_args()
    for path in emit(args.website, args.krkn_hub, args.krkn, args.source_ref):
        print(path)
    if args.scaffold:
        for line in scaffold(args.website, args.krkn_hub, args.krkn):
            print(line)


if __name__ == "__main__":
    main()
