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
