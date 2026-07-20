from bot import drift_scanner as ds


def _mk(tmp_path, env=None, krknctl=None, table=None, scenario="demo"):
    """Build a mini krkn-hub + website. Returns (krkn_hub_root, website_root)."""
    hub = tmp_path / "hub" / scenario
    hub.mkdir(parents=True)
    if env is not None:
        (hub / "env.sh").write_text(env, encoding="utf-8")
    if krknctl is not None:
        (hub / "krknctl-input.json").write_text(krknctl, encoding="utf-8")
    web = tmp_path / "web"
    (web / "content/en/docs/scenarios").mkdir(parents=True)
    if table is not None:
        d = web / "data/params" / scenario
        d.mkdir(parents=True)
        (d / "krkn-hub.yaml").write_text(table, encoding="utf-8")
    return tmp_path / "hub", web


def _hub(tmp_path, **kw):
    hub, web = _mk(tmp_path, **kw)
    return [f for f in ds.scenario_findings("demo", hub, web) if f.source == "krkn-hub"]


def test_missing_table(tmp_path):
    fs = _hub(tmp_path, env='export FOO=${FOO:="bar"}\n')
    assert [f.kind for f in fs] == ["missing-table"]
    assert "FOO" in fs[0].new


def test_stale_default(tmp_path):
    fs = _hub(tmp_path, env='export FOO=${FOO:="new"}\n',
              table="params:\n  - name: FOO\n    default: old\n")
    assert any(f.kind == "stale" and f.param == "FOO"
               and f.old == "old" and f.new == "new" for f in fs)


def test_missing_param(tmp_path):
    fs = _hub(tmp_path,
              env='export FOO=${FOO:="bar"}\nexport BAZ=${BAZ:="1"}\n',
              table="params:\n  - name: FOO\n    default: bar\n")
    assert any(f.kind == "missing" and f.param == "BAZ" and f.new == "1" for f in fs)


def test_extra_param(tmp_path):
    fs = _hub(tmp_path, env='export FOO=${FOO:="bar"}\n',
              table="params:\n  - name: FOO\n    default: bar\n  - name: OLD\n    default: x\n")
    assert any(f.kind == "extra" and f.param == "OLD" for f in fs)


def test_no_drift_when_table_matches(tmp_path):
    fs = _hub(tmp_path, env='export FOO=${FOO:="bar"}\n',
              table="params:\n  - name: FOO\n    default: bar\n")
    assert fs == []


def test_skips_global_params(tmp_path):
    hub, web = _mk(tmp_path, env='export WAIT_DURATION=${WAIT_DURATION:="0"}\n')
    # skip list comes from all-scenario-env.md; simulate it containing WAIT_DURATION
    md = web / "content/en/docs/scenarios/all-scenario-env.md"
    md.write_text("`WAIT_DURATION`\n", encoding="utf-8")
    fs = ds.scenario_findings("demo", hub, web)
    assert all(f.param != "WAIT_DURATION" for f in fs)


def test_format_report_structure_and_no_emdash(tmp_path):
    body = ds.format_report(_hub(tmp_path, env='export FOO=${FOO:="bar"}\n'))
    assert "—" not in body and "–" not in body and "→" not in body
    assert "#### demo" in body
    assert "- [ ]" in body
    assert "/fix demo" in body
    assert "source:" in body


def _box(body, scenario):
    import re
    m = re.search(rf"drift:{scenario} -->\n#### {scenario}\n(- \[.\])", body)
    return m.group(1)


def test_tick_preserved_per_scenario_not_by_shared_text():
    # two scenarios with identical summary text (both missing a krkn-hub table)
    a = ds.Finding("alpha", "krkn-hub", "missing-table", new="X", source_file="u", table_file="t")
    b = ds.Finding("beta", "krkn-hub", "missing-table", new="X", source_file="u", table_file="t")
    first = ds.format_report([a, b])
    assert first.count("- [ ]") == 2
    # tick only alpha
    prev = first.replace("#### alpha\n- [ ]", "#### alpha\n- [x]", 1)
    second = ds.format_report([a, b], prev_body=prev)
    assert _box(second, "alpha") == "- [x]"
    assert _box(second, "beta") == "- [ ]"   # shared text must NOT tick beta


def test_empty_findings_all_clear():
    assert ds.format_report([]) == "### Docs drift report\n\nNo drift found.\n"


def test_find_scenarios_from_markers(tmp_path):
    d = tmp_path / "content/en/docs/scenarios/node"
    d.mkdir(parents=True)
    (d / "_index.md").write_text('<krkn-hub-scenario id="node-scenarios" />\n', encoding="utf-8")
    assert ds.find_scenarios(tmp_path) == ["node-scenarios"]
