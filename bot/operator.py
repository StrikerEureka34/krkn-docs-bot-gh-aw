#!/usr/bin/env python3
"""Generate the krkn-operator API reference from its CRDs.

One data file per kind per section, and one page per kind. Every CRD field is
described at source, so the model is never called: the chain is wired anyway so
the day an undescribed field lands, the report says so instead of publishing a
blank cell."""
import argparse
from pathlib import Path

from bot.crd_parser import crd_columns, crd_fields, crd_meta, load_crd
from bot.descriptions import resolve_descriptions
from bot.emitter import emit_data_file, load_previous
from bot.report import write_report

CRD_GLOB = "config/crd/bases/*.yaml"
SECTION = "content/en/docs/krkn-operator/api-reference"
SOURCES = ("spec", "status", "columns")
# Marks a column's description as taken from the field its jsonPath names.
BORROW = "crd-field"
_HEADINGS = {"spec": "Spec", "status": "Status", "columns": "kubectl columns"}


def _no_model(scenario, names):
    """Nothing should reach the model. Returning {} turns an undescribed field
    into a reported gap rather than a silent blank."""
    return {}


def _records(doc):
    spec, status = crd_fields(doc, "spec"), crd_fields(doc, "status")
    by_section = {"spec": {r.name: r for r in spec},
                  "status": {r.name: r for r in status}}
    return {"spec": spec, "status": status,
            "columns": crd_columns(doc, by_section)}


def _emit_one(website_root, scenario, source, records, source_ref):
    out = website_root / "data" / "params" / scenario / f"{source}.yaml"
    prev = load_previous(out)
    # A borrow is re-derived every run so a column keeps following its field.
    existing = {n: p.get("description", "") for n, p in prev.items()
                if p.get("description_source") != BORROW}
    descs, gaps = resolve_descriptions(scenario, records, existing, _no_model,
                                       borrow_source=BORROW)
    emit_data_file(website_root, scenario, source, records, descs, source_ref)
    return out, [(scenario, source) + g for g in gaps]


def emit(website_root, operator_root, source_ref="HEAD"):
    """Write data/params/<plural>/<section>.yaml. Returns (paths, gaps)."""
    website_root = Path(website_root)
    written, gaps = [], []
    for path in sorted(Path(operator_root).glob(CRD_GLOB)):
        doc = load_crd(path)
        scenario = crd_meta(doc)["plural"]
        for source, records in _records(doc).items():
            if not records:
                continue
            out, g = _emit_one(website_root, scenario, source, records, source_ref)
            written.append(out)
            gaps += g
    return written, gaps


def _page(meta, sources):
    scope = "Namespaced" if meta["scope"] == "Namespaced" else "Cluster-scoped"
    head = f'`{meta["group"]}/{meta["version"]}` &ensp; {scope}'
    if meta["short"]:
        head += f' &ensp; short name `{meta["short"]}`'
    body = [
        "---",
        f'title: {meta["kind"]}',
        f'description: Fields of the {meta["kind"]} custom resource',
        f'weight: {meta["weight"]}',
        "---",
        "",
        head,
        "",
        "Generated from `config/crd/bases` in krkn-operator. Edit the Go doc"
        " comments there, not this page.",
        "",
    ]
    # The kind's own doc comment is deliberately not rendered. It is written for
    # Go readers and carries label syntax like <user|admin> that Hugo eats as raw
    # HTML, so prose here is a human's to add and the bot never overwrites it.
    for source in sources:
        body += [f'## {_HEADINGS[source]}', "",
                 f'{{{{< param-table scenario="{meta["plural"]}" '
                 f'source="{source}" >}}}}', ""]
    return "\n".join(body)


_INDEX_HEAD = """---
title: API Reference
description: Fields of every krkn-operator custom resource
weight: 6
---

The operator is driven by custom resources. These pages are generated from the
CRDs in krkn-operator, so a field here always matches the cluster.

To fix a description, edit the Go doc comment in `api/v1alpha1` upstream. The
next sync carries it here.

"""


def _index(metas):
    rows = ["| Kind | Short name | Fields |", "| --- | --- | --- |"]
    for m in metas:
        short = f'`{m["short"]}`' if m["short"] else "-"
        rows.append(f'| [{m["kind"]}]({m["plural"]}/) | {short} | {m["fields"]} |')
    return _INDEX_HEAD + "\n".join(rows) + "\n"


def scaffold(website_root, operator_root):
    """Write a page per kind plus the section index, each only when it does not
    exist. The bot never revisits a page, so prose added later survives."""
    website_root = Path(website_root)
    root = website_root / SECTION
    metas, written = [], []
    for path in sorted(Path(operator_root).glob(CRD_GLOB)):
        doc = load_crd(path)
        meta = crd_meta(doc)
        records = _records(doc)
        meta["fields"] = len(records["spec"]) + len(records["status"])
        metas.append(meta)
    # Alphabetical, so a new kind does not renumber the pages around it.
    metas.sort(key=lambda m: m["kind"])
    for i, meta in enumerate(metas, start=1):
        meta["weight"] = i
        sources = [s for s in SOURCES
                   if (website_root / "data" / "params" / meta["plural"]
                       / f"{s}.yaml").exists()]
        if not sources:
            continue
        page = root / f'{meta["plural"]}.md'
        if page.exists():
            continue
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(_page(meta, sources), encoding="utf-8")
        written.append(page)
    index = root / "_index.md"
    if metas and not index.exists():
        index.parent.mkdir(parents=True, exist_ok=True)
        index.write_text(_index(metas), encoding="utf-8")
        written.append(index)
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate the krkn-operator API reference")
    ap.add_argument("--operator", required=True, help="Path to the krkn-operator repo root")
    ap.add_argument("--website", default=".", help="Path to the website repo root")
    ap.add_argument("--source-ref", default="HEAD")
    ap.add_argument("--scaffold", action="store_true",
                    help="Also write any reference page that does not exist yet")
    args = ap.parse_args()
    crds = sorted(Path(args.operator).glob(CRD_GLOB))
    if not crds:
        raise FileNotFoundError(
            f"No CRDs under {Path(args.operator) / 'config/crd/bases'}. "
            "Point --operator at the krkn-operator repo root.")
    written, gaps = emit(args.website, args.operator, args.source_ref)
    for path in written:
        print(path)
    write_report(gaps)
    if args.scaffold:
        for path in scaffold(args.website, args.operator):
            print(path)


if __name__ == "__main__":
    main()
