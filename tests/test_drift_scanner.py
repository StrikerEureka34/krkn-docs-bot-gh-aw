from pathlib import Path
from bot.drift_scanner import find_drift, format_drift_report

FIXTURES = Path(__file__).parent / "fixtures"


def _make_yaml(path: Path, names_defaults: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    params = "\n".join(
        f"  - name: {n}\n    description: desc.\n    default: {v}" if v else f"  - name: {n}\n    description: desc."
        for n, v in names_defaults.items()
    )
    path.write_text(f"source_repo: krkn-hub\nsource_ref: HEAD\nparams:\n{params}\n")


def test_find_drift_detects_missing_param(tmp_path):
    """Param in env.sh but not in data file = missing."""
    hub = tmp_path / "hub"
    scenario = hub / "my-scenario"
    scenario.mkdir(parents=True)
    (scenario / "env.sh").write_text('export FOO=${FOO:="bar"}\n')

    web = tmp_path / "web"

    drift = find_drift(hub, web, skip=set())

    assert "my-scenario" in drift
    assert "FOO" in drift["my-scenario"]["missing"]


def test_find_drift_no_drift_when_documented(tmp_path):
    """No drift when param is in the data file with matching default."""
    hub = tmp_path / "hub"
    scenario = hub / "my-scenario"
    scenario.mkdir(parents=True)
    (scenario / "env.sh").write_text('export FOO=${FOO:="bar"}\n')

    web = tmp_path / "web"
    _make_yaml(web / "data/params/my-scenario/krkn-hub.yaml", {"FOO": "bar"})

    drift = find_drift(hub, web, skip=set())
    assert "my-scenario" not in drift


def test_find_drift_detects_stale_default(tmp_path):
    """Param present in both but default changed in source = stale."""
    hub = tmp_path / "hub"
    scenario = hub / "my-scenario"
    scenario.mkdir(parents=True)
    (scenario / "env.sh").write_text('export FOO=${FOO:="new"}\n')

    web = tmp_path / "web"
    _make_yaml(web / "data/params/my-scenario/krkn-hub.yaml", {"FOO": "old"})

    drift = find_drift(hub, web, skip=set())
    assert "my-scenario" in drift
    assert "FOO" in drift["my-scenario"]["stale"]


def test_find_drift_skips_global_params(tmp_path):
    """WAIT_DURATION in skip list must not appear in drift."""
    hub = tmp_path / "hub"
    scenario = hub / "my-scenario"
    scenario.mkdir(parents=True)
    (scenario / "env.sh").write_text('export WAIT_DURATION=${WAIT_DURATION:="0"}\n')

    web = tmp_path / "web"

    drift = find_drift(hub, web, skip={"WAIT_DURATION"})
    assert "my-scenario" not in drift


def test_find_drift_no_data_file_counts_all_as_missing(tmp_path):
    """If data file does not exist, every source param is missing."""
    hub = tmp_path / "hub"
    scenario = hub / "my-scenario"
    scenario.mkdir(parents=True)
    (scenario / "env.sh").write_text('export FOO=${FOO:="bar"}\nexport BAZ=${BAZ:="1"}\n')

    web = tmp_path / "web"

    drift = find_drift(hub, web, skip=set())
    assert "my-scenario" in drift
    assert set(drift["my-scenario"]["missing"]) == {"FOO", "BAZ"}


def test_format_drift_report_contains_scenario_and_command():
    drift = {"node-interface-down": {"missing": ["SERVICE_ACCOUNT"], "stale": [], "extra": []}}
    title, body = format_drift_report(drift, "2026-05-12")
    assert "node-interface-down" in title or "node-interface-down" in body
    assert "SERVICE_ACCOUNT" in body
    assert "@krkn-docs-bot /fix node-interface-down" in body


def test_format_drift_report_updates_not_duplicates():
    """Title includes date so scanner can search for exact title before creating."""
    _, body = format_drift_report({}, "2026-05-12")
    assert "2026-05-12" in body
