from unittest.mock import patch
import bot.doc_bot as doc_bot


def _write_env(scn_dir):
    scn_dir.mkdir(parents=True, exist_ok=True)
    (scn_dir / "env.sh").write_text(
        'export ACTION="${ACTION:-node_stop}"\n'
        'export NEW_ONE="${NEW_ONE:-x}"\n', encoding="utf-8")


def test_emit_then_reemit_is_byte_identical(tmp_path):
    hub = tmp_path / "hub"
    _write_env(hub / "node-scenarios")
    website = tmp_path / "site"
    (website / "content/en/docs/scenarios").mkdir(parents=True)
    (website / "content/en/docs/scenarios/all-scenario-env.md").write_text("", encoding="utf-8")

    doc_bot.run(scenario="node-scenarios", krkn_hub_root=hub, website_root=website)
    out = website / "data/params/node-scenarios/krkn-hub.yaml"
    first = out.read_text(encoding="utf-8")

    # Second run: every param already has a description in the file, so the
    # resolver must not be consulted again and the output stays byte-identical.
    with patch("bot.doc_bot._no_descriptions", side_effect=AssertionError("must not run")):
        doc_bot.run(scenario="node-scenarios", krkn_hub_root=hub, website_root=website)
    assert out.read_text(encoding="utf-8") == first
