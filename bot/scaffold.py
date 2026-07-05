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
    """Directory of the page whose _index.md declares this krkn-hub scenario id.
    Website page dir names diverge from source scenario names (node-cpu-hog ->
    hog-scenarios/cpu-hog-scenario), so the declared id is the reliable link."""
    root = Path(website_root) / "content/en/docs/scenarios"
    for index in root.rglob("_index.md"):
        m = _ID_RE.search(index.read_text(encoding="utf-8"))
        if m and m.group(1) == scenario:
            return index.parent
    return None


def _find_tab(website_root, scenario, source):
    scn_dir = _find_scenario_dir(website_root, scenario)
    if scn_dir is not None:
        tab = scn_dir / f"_tab-{source}.md"
        return tab if tab.exists() else None
    # Fallback for pages whose id is missing or disagrees with the source dir
    # name (e.g. site declares id="pvc-scenarios" for source "pvc-scenario").
    root = Path(website_root) / "content/en/docs/scenarios"
    for tab in root.rglob(f"_tab-{source}.md"):
        if tab.parent.name == scenario:
            return tab
    return None


def scaffold_scenario(scenario, website_root):
    """Inject the shortcode into the scenario's krkn-hub and krknctl tab files in place."""
    for source in ("krkn-hub", "krknctl"):
        tab = _find_tab(website_root, scenario, source)
        if tab is None:
            continue
        original = tab.read_text(encoding="utf-8")
        new = inject_shortcode(original, scenario, source)
        if new != original:
            tab.write_text(new, encoding="utf-8")
