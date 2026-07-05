import re
from pathlib import Path

_ID_RE = re.compile(r'<krkn-hub-scenario\s+id="([^"]+)"')


def _is_table_separator(line):
    s = line.strip().strip("|").strip()
    return bool(s) and "-" in s and all(c in "|-: " for c in s)


def inject_shortcode(text, scenario, source):
    """Replace the first markdown parameter table with the param-table shortcode call.
    Idempotent: returns text unchanged if a param-table call is already present."""
    call = f'{{{{< param-table scenario="{scenario}" source="{source}" >}}}}'
    if "param-table" in text:
        return text
    lines = text.splitlines(keepends=True)
    sep = end = None
    for i, line in enumerate(lines):
        if sep is None and _is_table_separator(line) and i > 0 and "|" in lines[i - 1]:
            sep = i
        elif sep is not None and "|" not in line:
            end = i
            break
    if sep is None:
        return text
    if end is None:
        end = len(lines)
    header = sep - 1
    return "".join(lines[:header] + [call + "\n"] + lines[end:])


def _find_scenario_dir(website_root, scenario):
    """Directory of the page for this scenario. Website page dir names diverge
    from source scenario names (node-cpu-hog -> hog-scenarios/cpu-hog-scenario),
    so the declared <krkn-hub-scenario id> is the reliable link. Falls back to an
    exact dir-name match for pages whose id is missing or disagrees with the
    source (e.g. id="pvc-scenarios" for source pvc-scenario)."""
    root = Path(website_root) / "content/en/docs/scenarios"
    for index in root.rglob("_index.md"):
        m = _ID_RE.search(index.read_text(encoding="utf-8"))
        if m and m.group(1) == scenario:
            return index.parent
    for index in root.rglob("_index.md"):
        if index.parent.name == scenario:
            return index.parent
    return None


def _find_tab(website_root, scenario, source):
    scn_dir = _find_scenario_dir(website_root, scenario)
    if scn_dir is None:
        return None
    tab = scn_dir / f"_tab-{source}.md"
    return tab if tab.exists() else None


# Provisional new-page layout. Confirm the frontmatter format with maintainers
# before relying on it (weight, description, overview prose are placeholders).
_INDEX_TEMPLATE = '''---
title: __TITLE__
description:
weight: 50
---

<krkn-hub-scenario id="__SCENARIO__">

TODO: scenario overview.

</krkn-hub-scenario>

{{< tabpane text=true >}}
  {{< tab header="**Krkn-hub**" lang="krkn-hub" >}}
{{< readfile file="_tab-krkn-hub.md" >}}
  {{< /tab >}}
  {{< tab header="**Krknctl**" lang="krknctl" >}}
{{< readfile file="_tab-krknctl.md" >}}
  {{< /tab >}}
{{< /tabpane >}}
'''


def _create_scenario_page(website_root, scenario):
    d = Path(website_root) / "content/en/docs/scenarios" / scenario
    d.mkdir(parents=True, exist_ok=True)
    title = scenario.replace("-", " ").title()
    index = _INDEX_TEMPLATE.replace("__TITLE__", title).replace("__SCENARIO__", scenario)
    (d / "_index.md").write_text(index, encoding="utf-8")
    return d


def scaffold_scenario(scenario, website_root):
    """Inject the param-table shortcode into the scenario's krkn-hub and krknctl
    tab files. If the scenario has no website page yet, create one (index plus
    stub tabs) first."""
    scn_dir = _find_scenario_dir(website_root, scenario)
    if scn_dir is None:
        scn_dir = _create_scenario_page(website_root, scenario)
    for source in ("krkn-hub", "krknctl"):
        tab = scn_dir / f"_tab-{source}.md"
        if not tab.exists():
            tab.write_text(f'{{{{< param-table scenario="{scenario}" source="{source}" >}}}}\n',
                           encoding="utf-8")
            continue
        original = tab.read_text(encoding="utf-8")
        new = inject_shortcode(original, scenario, source)
        if new != original:
            tab.write_text(new, encoding="utf-8")
