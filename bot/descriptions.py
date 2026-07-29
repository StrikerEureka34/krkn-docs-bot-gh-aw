def resolve_descriptions(scenario, records, existing, llm_fn):
    """Return (descriptions_by_name, names_sent_to_llm).

    Priority: source desc -> existing file desc -> LLM (residual only).

    Source first, deliberately. The order used to be existing first, to protect
    hand-edits, but the file it was protecting is stamped "Do not edit by hand".
    All it actually did was freeze descriptions at first generation: improving the
    wording in krknctl-input.json or an env.sh comment changed nothing downstream,
    because the committed data file always won. That makes a generated artifact
    authoritative over its own source, which is the opposite of what a sync bot is
    for. Every other field (default, type, possible_values) already takes source as
    truth; descriptions were the odd one out.

    The existing value stays as a fallback for params neither source describes,
    which today is the six krkn-hub-only ones like PORT and SIGNAL_ADDRESS.
    """
    out = {}
    residual = []
    for r in records:
        if r.description:
            out[r.name] = r.description
        elif r.name in existing and existing[r.name]:
            out[r.name] = existing[r.name]
        else:
            residual.append(r.name)
    if residual:
        generated = llm_fn(scenario, residual)
        for name in residual:
            # Blank, not a placeholder. "Configures port." reads as finished while
            # saying nothing, which hides the gap instead of showing it.
            out[name] = generated.get(name, "")
    return out, residual
