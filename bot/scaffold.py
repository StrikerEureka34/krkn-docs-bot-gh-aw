from pathlib import Path


def _is_table_separator(line):
    s = line.strip()
    return s.startswith("|") and all(c in "|-: " for c in s)


def inject_shortcode(text, scenario, source):
    """Replace the first markdown parameter table with the param-table shortcode call.
    Idempotent: returns text unchanged if a param-table call is already present."""
    call = f'{{{{< param-table scenario="{scenario}" source="{source}" >}}}}'
    if "param-table" in text:
        return text
    lines = text.splitlines(keepends=True)
    sep = end = None
    for i, line in enumerate(lines):
        if sep is None and _is_table_separator(line) and i > 0 and lines[i - 1].lstrip().startswith("|"):
            sep = i
        elif sep is not None and not line.strip().startswith("|"):
            end = i
            break
    if sep is None:
        return text
    if end is None:
        end = len(lines)
    header = sep - 1
    return "".join(lines[:header] + [call + "\n"] + lines[end:])


def _find_tab(website_root, scenario, source):
    root = Path(website_root) / "content/en/docs/scenarios"
    for tab in root.rglob(f"_tab-{source}.md"):
        if tab.parent.name == scenario or scenario in tab.parent.name:
            return tab
    return None


def scaffold_scenario(scenario, website_root):
    """Inject the shortcode into the scenario's krkn-hub and krknctl tab files in place."""
    for source in ("krkn-hub", "krknctl"):
        tab = _find_tab(website_root, scenario, source)
        if tab is None:
            continue
        new = inject_shortcode(tab.read_text(encoding="utf-8"), scenario, source)
        tab.write_text(new, encoding="utf-8")
