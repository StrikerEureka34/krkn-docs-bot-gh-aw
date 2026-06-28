def resolve_descriptions(scenario, records, existing, llm_fn):
    """Return (descriptions_by_name, names_sent_to_llm).
    Priority: existing file desc -> source desc -> LLM (residual only)."""
    out = {}
    residual = []
    for r in records:
        if r.name in existing and existing[r.name]:
            out[r.name] = existing[r.name]
        elif r.description:
            out[r.name] = r.description
        else:
            residual.append(r.name)
    if residual:
        generated = llm_fn(scenario, residual)
        for name in residual:
            out[name] = generated.get(name, f"Configures {name.replace('_', ' ').lower()}.")
    return out, residual
