_NO_SOURCE = "no description in any source and no published row"


def resolve_descriptions(scenario, records, existing, llm_fn, published=None):
    """Return (descriptions_by_name, gaps).

    Priority: source -> existing file -> published table -> LLM.

    The old order put existing first, to protect hand-edits. But the file it
    protected is stamped "Do not edit by hand", so all it did was freeze wording
    at first generation: a better description in krknctl-input.json never
    reached the docs. Every other field already takes the source as truth.

    published is the hand-written table the shortcode is about to replace, the
    last place a curated description survives. Only description and type are
    carried; a published default that disagrees with env.sh is drift, not a
    fallback.

    gaps is (name, filled_from, text) for every description not taken from a
    source file, where filled_from is "published-table", "llm", or "" with the
    reason in text. The existing-file rung is not a gap: it was reported on the
    run that first wrote it.
    """
    published = published or {}
    out, gaps, residual = {}, [], []
    for r in records:
        if r.description:
            out[r.name] = r.description
        elif existing.get(r.name):
            out[r.name] = existing[r.name]
        elif published.get(r.name):
            out[r.name] = published[r.name]
            r.description_source = "published-table"
            gaps.append((r.name, "published-table", out[r.name]))
        else:
            residual.append(r.name)
    if residual:
        generated = llm_fn(scenario, residual)
        by_name = {r.name: r for r in records}
        for name in residual:
            # Blank, not a placeholder. "Configures port." reads as finished
            # while saying nothing, which hides the gap.
            out[name] = generated.get(name, "")
            if out[name]:
                by_name[name].description_source = "llm"
                gaps.append((name, "llm", out[name]))
            else:
                gaps.append((name, "", _NO_SOURCE))
    return out, gaps
