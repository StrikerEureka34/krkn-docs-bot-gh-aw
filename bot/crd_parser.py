"""ParamRecords from a controller-gen CRD, the krkn-operator source.

Reads config/crd/bases/*.yaml, never the Go types: the YAML is generated from
those comments by `make manifests`, so it cannot disagree with the code."""
from pathlib import Path

import yaml

from bot.parser import ParamRecord

# ponytail: name heuristic. The upstream ask adds a real marker to the Go types;
# swap to that when it lands.
_SECRETISH = ("secret", "password", "token", "credential")


def _text(node):
    """controller-gen hard-wraps at 80 columns, so the raw value is multi-line
    and would break out of its table cell."""
    return " ".join((node.get("description") or "").split()) or None


def _default(node):
    """YAML gives a real bool, but a reader copies this into a manifest where
    Python's True is not valid."""
    if "default" not in node:
        return None
    value = node["default"]
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _allowed(node):
    # An array of enums carries them on items, not on the property.
    enum = node.get("enum") or (node.get("items") or {}).get("enum")
    return list(enum) if enum else None


def _record(path, node, required):
    description = _text(node)
    return ParamRecord(
        name=path,
        description=description,
        # Same standing as an env.sh comment: the source describes itself, so it
        # is not a fallback and the emitter does not record it.
        description_source="crd" if description else None,
        type=node.get("type"),
        default=_default(node),
        required=required,
        allowed_values=_allowed(node),
        secret=any(s in path.lower() for s in _SECRETISH),
    )


def _walk(schema, prefix, out):
    """Every object level carries its own `required` list, so it is read here
    rather than once at the top."""
    required = set(schema.get("required") or ())
    for name, node in (schema.get("properties") or {}).items():
        path = f"{prefix}{name}"
        out.append(_record(path, node, name in required))
        _descend(node, path, out)


def _descend(node, path, out):
    """The three containers compose, so this recurses rather than checking each
    once: targetData is a map of arrays of objects. <key> stands in for a map key,
    which is the user's own string and cannot be named."""
    if node.get("properties"):
        _walk(node, f"{path}.", out)
    value = node.get("additionalProperties")
    if isinstance(value, dict):
        _descend(value, f"{path}.<key>", out)
    items = node.get("items")
    if isinstance(items, dict):
        _descend(items, f"{path}[]", out)


def _schema(doc):
    return doc["spec"]["versions"][0]["schema"]["openAPIV3Schema"]


def crd_fields(doc, section) -> list[ParamRecord]:
    """Records for one of "spec" or "status", empty when the kind has no status."""
    node = (_schema(doc).get("properties") or {}).get(section)
    if not node:
        return []
    out = []
    _walk(node, "", out)
    return out


def crd_columns(doc, by_section) -> list[ParamRecord]:
    """Records for the `kubectl get` columns.

    A column has no description of its own, so it borrows from the field its
    jsonPath names. by_section is {"spec": {name: record}, "status": {...}}."""
    out = []
    for column in doc["spec"]["versions"][0].get("additionalPrinterColumns") or ():
        path = column.get("jsonPath", "")
        # .metadata.creationTimestamp is the Age column every kind carries.
        if path.startswith(".metadata."):
            continue
        section, _, field = path.lstrip(".").partition(".")
        match = (by_section.get(section) or {}).get(field)
        record = ParamRecord(
            name=column["name"],
            type=column.get("type"),
            # Requiredness is meaningless for a display column, and None keeps
            # the emitter from adding a column of "No".
            required=None,
        )
        if match and match.description:
            record.borrowed_description = match.description
        out.append(record)
    return out


def crd_meta(doc) -> dict:
    """What the reference page needs in its heading."""
    spec, names = doc["spec"], doc["spec"]["names"]
    short = names.get("shortNames") or []
    return {
        "kind": names["kind"],
        "plural": names["plural"],
        "short": short[0] if short else None,
        "group": spec["group"],
        "version": spec["versions"][0]["name"],
        "scope": spec["scope"],
        "description": _text(_schema(doc)),
    }


def load_crd(path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))
