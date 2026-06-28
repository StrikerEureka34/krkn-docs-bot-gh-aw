from bot.scaffold import inject_shortcode

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
