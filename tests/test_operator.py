import shutil
from pathlib import Path

import pytest
import yaml

from bot import operator

CRDS = Path(__file__).parent / "fixtures" / "crd"


@pytest.fixture
def repo(tmp_path):
    """A krkn-operator checkout, as the bot sees it: only the CRDs matter."""
    bases = tmp_path / "operator" / "config" / "crd" / "bases"
    bases.mkdir(parents=True)
    for f in CRDS.glob("*.yaml"):
        shutil.copy(f, bases)
    (tmp_path / "website").mkdir()
    return tmp_path


def run(repo, scaffold=True):
    written, gaps = operator.emit(repo / "website", repo / "operator")
    pages = operator.scaffold(repo / "website", repo / "operator") if scaffold else []
    return written, gaps, pages


def test_a_full_run_writes_a_file_per_section_per_kind(repo):
    written, _, _ = run(repo)
    assert len(written) == 25
    data = repo / "website" / "data" / "params"
    assert (data / "krknusers" / "spec.yaml").exists()
    assert (data / "krknusers" / "columns.yaml").exists()


def test_a_kind_with_no_status_gets_no_status_file(repo):
    run(repo)
    data = repo / "website" / "data" / "params" / "krknusergroups"
    assert not (data / "status.yaml").exists()
    assert (data / "spec.yaml").exists()


def test_every_row_is_described_without_the_model(repo):
    """The claim the whole source rests on: the CRDs describe themselves, so a
    full run never calls out."""
    calls = []
    original = operator._no_model
    operator._no_model = lambda s, n: calls.append(n) or {}
    try:
        written, gaps, _ = run(repo)
    finally:
        operator._no_model = original
    rows = [p for f in written
            for p in yaml.safe_load(Path(f).read_text(encoding="utf-8"))["params"]]
    assert len(rows) == 167
    assert [r["name"] for r in rows if not r["description"]] == []
    assert calls == []
    assert gaps == []


def test_only_the_borrowed_column_rows_carry_provenance(repo):
    written, _, _ = run(repo)
    marked = [(Path(f).name, p["name"]) for f in written
              for p in yaml.safe_load(Path(f).read_text(encoding="utf-8"))["params"]
              if p.get("description_source")]
    # A field describes itself, so only a column can be a borrow.
    assert len(marked) == 26
    assert {f for f, _ in marked} == {"columns.yaml"}


def test_a_second_run_changes_nothing(repo):
    written, _, _ = run(repo)
    before = {f: Path(f).read_bytes() for f in written}
    pages_before = {p: Path(p).read_bytes()
                    for p in (repo / "website").rglob("api-reference/*.md")}
    run(repo)
    assert {f: Path(f).read_bytes() for f in written} == before
    assert {p: Path(p).read_bytes()
            for p in (repo / "website").rglob("api-reference/*.md")} == pages_before


def test_a_page_edited_by_hand_survives_the_next_run(repo):
    """The guarantee: the bot owns the data files, humans own the markdown."""
    run(repo)
    page = repo / "website" / operator.SECTION / "krknusers.md"
    edited = page.read_text(encoding="utf-8") + "\n## Notes\n\nAdded by a human.\n"
    page.write_text(edited, encoding="utf-8")
    run(repo)
    assert page.read_text(encoding="utf-8") == edited


def test_a_changed_description_moves_exactly_one_row(repo):
    run(repo)
    spec = repo / "website" / "data" / "params" / "krknusers" / "spec.yaml"
    before = spec.read_text(encoding="utf-8").splitlines()
    crd = repo / "operator" / "config" / "crd" / "bases" / \
        "krkn.krkn-chaos.dev_krknusers.yaml"
    crd.write_text(crd.read_text(encoding="utf-8").replace(
        "Surname is the last name of the user", "Family name of the user"),
        encoding="utf-8")
    run(repo)
    after = spec.read_text(encoding="utf-8").splitlines()
    differing = [(a, b) for a, b in zip(before, after) if a != b]
    assert len(differing) == 1
    assert "Family name of the user" in differing[0][1]


def test_pages_are_written_once_per_kind_plus_an_index(repo):
    _, _, pages = run(repo)
    assert len(pages) == 10
    names = sorted(Path(p).name for p in pages)
    assert "_index.md" in names
    assert "krknusers.md" in names


def test_a_page_calls_only_the_sources_that_have_data(repo):
    """krknusergroups has no status, so its page must not call a table that
    would fail the Hugo build."""
    run(repo)
    page = (repo / "website" / operator.SECTION / "krknusergroups.md").read_text(
        encoding="utf-8")
    assert 'source="spec"' in page
    assert 'source="columns"' in page
    assert 'source="status"' not in page


def test_the_page_heading_names_the_api_and_short_name(repo):
    run(repo)
    page = (repo / "website" / operator.SECTION / "krknusers.md").read_text(
        encoding="utf-8")
    assert "`krkn.krkn-chaos.dev/v1alpha1`" in page
    assert "short name `ku`" in page
    assert "title: KrknUser" in page


def test_the_go_doc_comment_is_not_rendered_into_the_page(repo):
    """It carries label syntax like <user|admin> that Hugo eats as raw HTML."""
    run(repo)
    page = (repo / "website" / operator.SECTION / "krknusers.md").read_text(
        encoding="utf-8")
    assert "<user|admin>" not in page


def test_an_operator_path_with_no_crds_is_an_error(tmp_path, monkeypatch):
    """Pointing --operator at the wrong directory would otherwise write nothing
    and report success."""
    (tmp_path / "website").mkdir()
    monkeypatch.setattr("sys.argv", ["operator", "--operator", str(tmp_path),
                                     "--website", str(tmp_path / "website")])
    with pytest.raises(FileNotFoundError, match="No CRDs"):
        operator.main()
