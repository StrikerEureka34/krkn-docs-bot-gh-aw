#!/usr/bin/env python3
"""Generate the two global parameter pages from their sources.

krknctl globals come from krkn/containers/krknctl-input.json, which carries a
"group" field and is displayed by CLI flag name. krkn-hub globals come from
krkn-hub/env.sh, which has no grouping of its own: it borrows one by joining
each export name against the krknctl "variable" field. Exports that do not join
land in a single "other" group.

Section headings and their order live in the website page, not here. The page
writes its own heading and then calls the shortcode for that group.
"""
from pathlib import Path

from bot.parser import extract_env_params, extract_krknctl_params

GLOBAL_SCENARIO = "globals"
OTHER_GROUP = "other"
_KRKNCTL_REL = "containers/krknctl-input.json"


def build_groups(krkn_hub_root, krkn_root):
    """(krknctl_records, env_records), both with .group populated.

    krknctl records are keyed on the CLI flag because that is what its page
    displays. env records keep the variable name and borrow the group, and a
    description, from the matching krknctl entry when they have none of their own."""
    ctl_path = Path(krkn_root) / _KRKNCTL_REL
    by_flag = extract_krknctl_params(ctl_path, key="name")
    by_var = {r.name: r for r in extract_krknctl_params(ctl_path)}

    env_path = Path(krkn_hub_root) / "env.sh"
    env = extract_env_params(env_path) if env_path.exists() else []
    for r in env:
        match = by_var.get(r.name)
        r.group = match.group if match and match.group else OTHER_GROUP
        # An inline comment in env.sh is krkn-hub's own wording, so it wins.
        if not r.description and match and match.description:
            r.description = match.description
            r.description_source = "krknctl"
    return by_flag, env
