import yaml
import json

from bot import globals as g


def _sources(tmp_path, env, ctl):
    """Build a mini krkn-hub + krkn. Returns (krkn_hub_root, krkn_root)."""
    hub = tmp_path / "hub"
    hub.mkdir()
    (hub / "env.sh").write_text(env, encoding="utf-8")
    containers = tmp_path / "krkn" / "containers"
    containers.mkdir(parents=True)
    (containers / "krknctl-input.json").write_text(json.dumps(ctl), encoding="utf-8")
    return hub, tmp_path / "krkn"


CTL = [{"name": "cerberus-enabled", "variable": "CERBERUS_ENABLED", "group": "cerberus",
        "default": "False", "description": "Enables Cerberus Support"}]

CERBERUS = 'export CERBERUS_ENABLED=${CERBERUS_ENABLED:=False}\n'


def test_env_export_borrows_its_group_from_the_join(tmp_path):
    hub, krkn = _sources(tmp_path, CERBERUS, CTL)
    _, env = g.build_groups(hub, krkn)
    assert env[0].group == "cerberus"


def test_env_export_borrows_a_description_when_it_has_no_comment(tmp_path):
    hub, krkn = _sources(tmp_path, CERBERUS, CTL)
    _, env = g.build_groups(hub, krkn)
    assert env[0].description == "Enables Cerberus Support"


def test_own_comment_beats_the_joined_description(tmp_path):
    hub, krkn = _sources(tmp_path, CERBERUS.rstrip("\n") + "  # Local wording\n", CTL)
    _, env = g.build_groups(hub, krkn)
    assert env[0].description == "Local wording"


def test_unjoined_export_lands_in_other(tmp_path):
    """RETRY_WAIT is krkn-hub only, krknctl does not expose it."""
    hub, krkn = _sources(tmp_path, 'export RETRY_WAIT=${RETRY_WAIT:=120}\n', CTL)
    _, env = g.build_groups(hub, krkn)
    assert env[0].group == "other"


def test_krknctl_side_is_keyed_on_the_cli_flag(tmp_path):
    """Its page renders --cerberus-enabled, not CERBERUS_ENABLED."""
    hub, krkn = _sources(tmp_path, "", CTL)
    ctl, _ = g.build_groups(hub, krkn)
    assert ctl[0].name == "cerberus-enabled"
    assert ctl[0].group == "cerberus"


def test_emits_one_file_per_source_not_per_group(tmp_path):
    """Grouping is data, not filenames: a new upstream group must not add a file."""
    hub, krkn = _sources(tmp_path, 'export RETRY_WAIT=${RETRY_WAIT:=120}\n', CTL)
    web = tmp_path / "web"
    g.emit(web, hub, krkn)
    d = web / "data/params/globals"
    assert sorted(p.name for p in d.iterdir()) == ["krkn-hub.yaml", "krknctl.yaml"]


def test_every_param_carries_its_group(tmp_path):
    hub, krkn = _sources(tmp_path, 'export RETRY_WAIT=${RETRY_WAIT:=120}\n', CTL)
    web = tmp_path / "web"
    g.emit(web, hub, krkn)
    rows = yaml.safe_load((web / "data/params/globals/krkn-hub.yaml").read_text())["params"]
    assert {r["name"]: r["group"] for r in rows} == {"RETRY_WAIT": "other"}
    ctl = yaml.safe_load((web / "data/params/globals/krknctl.yaml").read_text())["params"]
    assert ctl[0]["group"] == "cerberus"


def test_a_source_description_change_reaches_the_data_file(tmp_path):
    """Superseded: this used to assert the committed file beat the source, so
    improving the wording upstream changed nothing downstream. Source wins now.
    Better wording belongs in krknctl-input.json, where every consumer gets it."""
    hub, krkn = _sources(tmp_path, "", CTL)
    web = tmp_path / "web"
    out = web / "data/params/globals/krknctl.yaml"
    out.parent.mkdir(parents=True)
    out.write_text("params:\n  - name: cerberus-enabled\n    description: stale wording\n",
                   encoding="utf-8")
    g.emit(web, hub, krkn)
    assert yaml.safe_load(out.read_text())["params"][0]["description"] == "Enables Cerberus Support"


def test_regenerating_twice_is_byte_identical(tmp_path):
    hub, krkn = _sources(tmp_path, CERBERUS, CTL)
    web = tmp_path / "web"
    g.emit(web, hub, krkn)
    first = (web / "data/params/globals/krkn-hub.yaml").read_text()
    g.emit(web, hub, krkn)
    assert (web / "data/params/globals/krkn-hub.yaml").read_text() == first


PAGE = """## Cerberus

Blurb.

| Parameter | Description | Default |
|-----------|-------------|---------|
| `--cerberus-enabled` | Enables it | False |
"""


def test_scaffold_injects_into_the_global_pages(tmp_path):
    hub, krkn = _sources(tmp_path, "", CTL)
    web = tmp_path / "web"
    d = web / "content/en/docs/scenarios"
    d.mkdir(parents=True)
    (d / "all-scenario-env-krknctl.md").write_text(PAGE, encoding="utf-8")
    report = g.scaffold(web, hub, krkn)
    out = (d / "all-scenario-env-krknctl.md").read_text()
    assert 'group="cerberus"' in out
    assert "Blurb." in out, "prose must survive"
    assert any("cerberus" in r for r in report), report


def test_scaffold_tolerates_a_missing_page(tmp_path):
    hub, krkn = _sources(tmp_path, "", CTL)
    web = tmp_path / "web"
    (web / "content/en/docs/scenarios").mkdir(parents=True)
    assert g.scaffold(web, hub, krkn) == []
