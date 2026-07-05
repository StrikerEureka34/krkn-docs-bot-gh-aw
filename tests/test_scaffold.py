from bot.scaffold import inject_shortcode, scaffold_scenario


def _data(website, scenario, source="krkn-hub"):
    d = website / "data/params" / scenario
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{source}.yaml").write_text("params: []\n", encoding="utf-8")


def _make_page(website, relpath, source_id=None, tab_source="krkn-hub"):
    d = website / "content/en/docs/scenarios" / relpath
    d.mkdir(parents=True, exist_ok=True)
    idx = "---\ntitle: X\n---\n"
    if source_id is not None:
        idx += f'<krkn-hub-scenario id="{source_id}">\n</krkn-hub-scenario>\n'
    (d / "_index.md").write_text(idx, encoding="utf-8")
    tab = d / f"_tab-{tab_source}.md"
    tab.write_text(
        "#### Supported parameters\n\n"
        "| Parameter | Description | Default |\n"
        "| --------- | ----------- | ------- |\n"
        "| ACTION | Action to run. | x |\n\n"
        "keep this prose.\n",
        encoding="utf-8",
    )
    return tab


def test_scaffold_finds_page_by_krkn_hub_id_when_dir_name_differs(tmp_path):
    website = tmp_path / "site"
    tab = _make_page(website, "hog-scenarios/cpu-hog-scenario", source_id="node-cpu-hog")
    _data(website, "node-cpu-hog", "krkn-hub")
    scaffold_scenario("node-cpu-hog", website)
    out = tab.read_text(encoding="utf-8")
    assert '{{< param-table scenario="node-cpu-hog" source="krkn-hub" >}}' in out
    assert "| ACTION |" not in out
    assert "keep this prose." in out


def test_scaffold_falls_back_to_dir_name_when_id_disagrees(tmp_path):
    website = tmp_path / "site"
    tab = _make_page(website, "pvc-scenario", source_id="pvc-scenarios")
    _data(website, "pvc-scenario", "krkn-hub")
    scaffold_scenario("pvc-scenario", website)
    assert '{{< param-table scenario="pvc-scenario" source="krkn-hub" >}}' in tab.read_text(encoding="utf-8")


def test_scaffold_does_not_match_dir_name_by_substring(tmp_path):
    website = tmp_path / "site"
    tab = _make_page(website, "node-scenarios", source_id="node-scenarios")
    scaffold_scenario("node", website)
    assert "param-table" not in tab.read_text(encoding="utf-8")


def test_scaffold_creates_page_when_none_exists(tmp_path):
    website = tmp_path / "site"
    (website / "content/en/docs/scenarios").mkdir(parents=True)
    _data(website, "brand-new-scenario", "krkn-hub")
    _data(website, "brand-new-scenario", "krknctl")
    scaffold_scenario("brand-new-scenario", website)
    page = website / "content/en/docs/scenarios/brand-new-scenario"
    idx = (page / "_index.md").read_text(encoding="utf-8")
    assert '<krkn-hub-scenario id="brand-new-scenario">' in idx
    assert 'readfile file="_tab-krkn-hub.md"' in idx
    krkn_hub_tab = (page / "_tab-krkn-hub.md").read_text(encoding="utf-8")
    assert '{{< param-table scenario="brand-new-scenario" source="krkn-hub" >}}' in krkn_hub_tab
    krknctl_tab = (page / "_tab-krknctl.md").read_text(encoding="utf-8")
    assert '{{< param-table scenario="brand-new-scenario" source="krknctl" >}}' in krknctl_tab


def test_scaffold_only_creates_tabs_for_sources_with_data(tmp_path):
    website = tmp_path / "site"
    (website / "content/en/docs/scenarios").mkdir(parents=True)
    _data(website, "rollback", "krknctl")   # only krknctl has data, no env params
    scaffold_scenario("rollback", website)
    page = website / "content/en/docs/scenarios/rollback"
    assert (page / "_tab-krknctl.md").exists()
    assert not (page / "_tab-krkn-hub.md").exists()
    idx = (page / "_index.md").read_text(encoding="utf-8")
    assert 'readfile file="_tab-krknctl.md"' in idx
    assert 'readfile file="_tab-krkn-hub.md"' not in idx

TAB = """\
#### Supported parameters

| Parameter | Description | Type | Default |
| --------- | ----------- | ---- | ------- |
| ACTION | Action to run. | enum | node_stop |

**NOTE** keep this prose.
"""


def test_replaces_table_with_shortcode_and_keeps_prose():
    out = inject_shortcode(TAB, scenario="node-scenarios", source="krkn-hub")
    assert '{{< param-table scenario="node-scenarios" source="krkn-hub" >}}' in out
    assert "| ACTION |" not in out
    assert "#### Supported parameters" in out
    assert "**NOTE** keep this prose." in out


def test_idempotent_when_already_migrated():
    once = inject_shortcode(TAB, "node-scenarios", "krkn-hub")
    twice = inject_shortcode(once, "node-scenarios", "krkn-hub")
    assert once == twice


BARE_TAB = """\
#### Supported parameters

See list of variables [here](all-scenario-env.md)

Parameter               | Description                   | Type   | Default
----------------------- | ----------------------------- | ------ | -------
ACTION                  | Action to run.                | enum   | node_stop_start_scenario
LABEL_SELECTOR          | Node label to target          | string | node-role.kubernetes.io/worker

{{% alert title="Note" %}} some note {{% /alert %}}
"""


def test_bare_table_replaced():
    out = inject_shortcode(BARE_TAB, "node-scenarios", "krkn-hub")
    assert '{{< param-table scenario="node-scenarios" source="krkn-hub" >}}' in out
    assert "ACTION" not in out
    assert "#### Supported parameters" in out
    assert "{{% alert" in out


def test_bare_table_idempotent():
    once = inject_shortcode(BARE_TAB, "node-scenarios", "krkn-hub")
    twice = inject_shortcode(once, "node-scenarios", "krkn-hub")
    assert once == twice
