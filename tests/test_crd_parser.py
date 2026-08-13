from pathlib import Path

import pytest

from bot.crd_parser import crd_columns, crd_fields, crd_meta, load_crd

CRDS = Path(__file__).parent / "fixtures" / "crd"


def crd(kind):
    return load_crd(CRDS / f"krkn.krkn-chaos.dev_{kind}.yaml")


def by_name(records):
    return {r.name: r for r in records}


def sections(doc):
    spec, status = crd_fields(doc, "spec"), crd_fields(doc, "status")
    return {"spec": by_name(spec), "status": by_name(status)}


# The headline number, guarded. Every field described at source is what lets the
# operator skip the model entirely.
def test_every_field_across_every_crd_is_described():
    fields = [r for f in sorted(CRDS.glob("*.yaml"))
              for s in ("spec", "status") for r in crd_fields(load_crd(f), s)]
    assert len(fields) == 141
    undescribed = [r.name for r in fields if not r.description]
    assert undescribed == []


def test_every_column_borrows_a_description():
    total, borrowed = 0, 0
    for f in sorted(CRDS.glob("*.yaml")):
        doc = load_crd(f)
        for c in crd_columns(doc, sections(doc)):
            total += 1
            borrowed += bool(c.borrowed_description)
    assert (total, borrowed) == (26, 26)


def test_the_age_column_is_skipped():
    """Every kind carries .metadata.creationTimestamp as Age, which documents
    Kubernetes rather than krkn."""
    doc = crd("krknusers")
    names = [c.name for c in crd_columns(doc, sections(doc))]
    assert "Age" not in names
    assert names == ["UserID", "Name", "Surname", "Role", "Active"]


def test_a_column_borrows_from_the_field_its_jsonpath_names():
    doc = crd("krknusers")
    active = next(c for c in crd_columns(doc, sections(doc)) if c.name == "Active")
    assert active.borrowed_description == \
        "Active indicates whether the user account is active"


def test_a_column_pointing_nowhere_is_left_blank_not_guessed(monkeypatch):
    """A jsonPath the walk cannot reach must surface as a gap, not a wrong cell."""
    doc = crd("krknusers")
    doc["spec"]["versions"][0]["additionalPrinterColumns"] = [
        {"jsonPath": ".spec.doesNotExist", "name": "Ghost", "type": "string"}]
    ghost = crd_columns(doc, sections(doc))[0]
    assert ghost.name == "Ghost"
    assert ghost.borrowed_description is None
    assert ghost.description is None


def test_a_column_carries_no_requiredness():
    """Requiredness is meaningless for a display column, and None is what stops
    the emitter adding a column of "No"."""
    doc = crd("krknusers")
    assert all(c.required is None for c in crd_columns(doc, sections(doc)))


def test_a_hard_wrapped_description_comes_back_as_one_line():
    """controller-gen wraps at 80 columns. Raw, it breaks out of a table cell."""
    spec = by_name(crd_fields(crd("krknusers"), "spec"))
    assert spec["passwordSecretRef"].description == (
        "PasswordSecretRef references the Secret containing the hashed password "
        "The Secret must contain a 'passwordHash' key with the bcrypt hash")


def test_an_enum_and_a_default_both_survive():
    role = by_name(crd_fields(crd("krknusers"), "spec"))["role"]
    assert role.allowed_values == ["user", "admin"]
    assert role.default == "user"


def test_an_array_takes_its_enum_from_items():
    """actions is an array of enum strings, so the values sit on items, not on
    the property itself."""
    spec = by_name(crd_fields(crd("krknusergroups"), "spec"))
    assert spec["clusterPermissions.<key>.actions"].allowed_values == \
        ["view", "run", "cancel"]


def test_a_boolean_default_is_not_rendered_as_python():
    """YAML gives a real bool, and a reader copies this into a manifest."""
    status = by_name(crd_fields(crd("krknusers"), "status"))
    assert status["active"].default == "true"


def test_required_is_read_from_the_parent_not_the_top():
    spec = by_name(crd_fields(crd("krknusers"), "spec"))
    assert spec["name"].required is True
    assert spec["organization"].required is False


def test_required_is_read_at_each_nested_level():
    spec = by_name(crd_fields(crd("krknusergroups"), "spec"))
    assert spec["clusterPermissions.<key>.actions"].required is True


def test_a_map_of_objects_is_flattened_with_a_key_marker():
    spec = by_name(crd_fields(crd("krknusergroups"), "spec"))
    assert "clusterPermissions" in spec
    assert "clusterPermissions.<key>.actions" in spec


def test_a_map_of_arrays_of_objects_is_reached():
    """targetData is map -> array -> object. The three containers compose, so a
    walk that checks each once at a single level loses both leaves."""
    status = by_name(crd_fields(crd("krkntargetrequests"), "status"))
    assert "targetData.<key>[].cluster-name" in status
    assert "targetData.<key>[].cluster-api-url" in status


def test_a_secret_bearing_name_is_marked():
    spec = by_name(crd_fields(crd("krknusers"), "spec"))
    assert spec["passwordSecretRef"].secret is True
    assert spec["name"].secret is False


def test_kubernetes_boilerplate_is_not_a_parameter():
    """apiVersion, kind and metadata sit beside spec and status on every kind."""
    spec = by_name(crd_fields(crd("krknusers"), "spec"))
    assert not {"apiVersion", "kind", "metadata"} & set(spec)


def test_a_kind_with_no_status_yields_no_status_records():
    assert crd_fields(crd("krknusergroups"), "status") == []


def test_meta_carries_what_the_page_heading_needs():
    m = crd_meta(crd("krknusers"))
    assert m["kind"] == "KrknUser"
    assert m["plural"] == "krknusers"
    assert m["short"] == "ku"
    assert m["group"] == "krkn.krkn-chaos.dev"
    assert m["version"] == "v1alpha1"
    assert m["scope"] == "Namespaced"
    assert m["description"].startswith("KrknUser is the Schema")


@pytest.mark.parametrize("kind,plural", [
    ("krknusers", "krknusers"), ("krkngraphruns", "krkngraphruns"),
    ("krknscenarioruns", "krknscenarioruns"),
])
def test_the_plural_is_already_lowercase_so_it_can_be_a_scenario_key(kind, plural):
    assert crd_meta(crd(kind))["plural"] == plural
