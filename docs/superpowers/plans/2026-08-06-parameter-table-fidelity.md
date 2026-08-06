# Parameter Table Fidelity Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** make the generated parameter tables match or beat the hand-written ones they replace, and make it impossible for the bot to replace a filled cell with an empty one.

**Architecture:** a fallback chain, not a gate. Five additive changes to the data and the shortcode, then a published-table rung that survives regeneration, then a model rung called from Python inside the existing pre-agent step. `name` in the data files stays the env var throughout, so `drift_scanner` and `build_skip_list` need no changes. The gh-aw agent is not touched: its prompt, turn budget and tool grants stay exactly as they are.

**Tech Stack:** Python 3.11, pytest, PyYAML, Hugo (extended) with Go templates, gh-aw 0.80.9.

---

## Where this runs

Implement in `krkn-docs-bot-gh-aw`. That is the repo `doc-sync.md` pip-installs from, so a fork test picks the change up on the next run with no redeploy.

Port to `krkn-chaos/docsync-bot` as a PR once #17 to #21 land. The Hugo shortcode test harness (`tests/conftest.py` `Site` fixture and `tests/test_param_table.py`) exists **only** in docsync-bot, so shortcode assertions get written during that port. In gh-aw, verify the shortcode by rendering the real site:

```bash
cd /c/Users/nayus/Desktop/LFX/krkn_Sync/website
./node_modules/hugo-extended/vendor/hugo.exe --logLevel warn --destination public-test
```

Run the bot tests from the repo root:

```bash
cd /c/Users/nayus/Desktop/LFX/krkn_Sync/krkn-docs-bot-gh-aw/krkn-docs-bot-gh-aw
python -m pytest -q
```

Baseline before starting: **124 passed** (verified).

---

## File structure

| File | Responsibility after this change |
| --- | --- |
| `bot/parser.py` | Reads `secret` off krknctl entries. `ParamRecord` gains one field. |
| `bot/emitter.py` | Emits `flag` (only when it differs from `name`), `secret` and `description_source`. Reads all three back. |
| `bot/descriptions.py` | Owns the whole chain. Gains a published-table rung and a model rung, stamps provenance, returns a gap list. |
| `bot/doc_bot.py` | The krknctl join carries `type`. Resolves tabs via `_find_tab`. Assembles model context. Collects gaps. |
| `bot/globals.py` | One change: passes the two global pages' tables into `resolve_descriptions`. |
| `bot/scaffold.py` | Owns the published-table reader, over every table on a page. Passes `prefix="--"` per scenario. |
| `bot/describe.py` (new) | The model call. Assembles nothing, validates everything, fails soft. |
| `bot/report.py` (new) | Builds the commit-message sections and escapes table cells. |
| `website-template/layouts/shortcodes/param-table.html` | Renders `flag`, marks secrets, orders and blanks columns. |
| `.github/workflows/doc-sync.md` | Passes endpoint env to the generate step; appends the gap report to the commit message from a file. |

`bot/drift_scanner.py` is untouched. If it needs editing, section 7 of the spec is wrong and should be revisited rather than patched around.

`bot/globals.py` forked the load-existing / resolve / emit sequence from `doc_bot`, so it misses every improvement made to the other copy. Measured through `build_groups`: the 78 krknctl global records are complete, but 6 of the 75 krkn-hub ones have no description from any source and at least three have curated text on the published page. It gets the carry-forward rung in Task 8 and nothing else. Unifying the two emit paths is out of scope.

**Three facts that make this cheap, all verified:**

1. `resolve_descriptions` returns `(descriptions, residual)` and *both* callers discard the second element with `descs, _ =` (`bot/doc_bot.py:31`, `bot/globals.py:75`). Its shape can change freely. Adding keyword arguments with defaults keeps `globals.py` compiling untouched.
2. Custom `steps:` run **outside** the firewall. They compile to lock lines 523-620; AWF is installed at 625 and only wraps the agent execution at 938. The model call needs no `network.allowed` entry.
3. `COPILOT_GITHUB_TOKEN` is already a declared secret (lock line 237) and gh-aw excludes it from the agent sandbox (`--exclude-env COPILOT_GITHUB_TOKEN`, line 988), so it is a runner-level secret available to those steps.

**Names to get right**, since an earlier draft got several wrong:

| Thing | Correct reference |
| --- | --- |
| Description-resolution tests | `tests/test_description_resolution.py`, **not** `test_descriptions.py` |
| The no-op llm function | `_no_descriptions` (in `doc_bot.py` and `globals.py`); tests use `fake_llm` and an inline `lambda s, n: {}` |
| A page fixture with one table | `TAB` at `tests/test_scaffold.py:83` |
| Globals emit | `tests/test_globals.py` does `from bot import globals as g`, then `g.emit(...)` |

---

## Chunk 1: Data and rendering

### Task 1: Emit the CLI flag on krknctl rows

**Files:**
- Modify: `bot/emitter.py` (`_param_dict`)
- Test: `tests/test_emitter.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_krknctl_rows_carry_the_cli_flag():
    """The krknctl page lists flags, but name stays the env var so the drift
    scanner and the skip list keep matching on it."""
    recs = [ParamRecord(name="ACTION", flag="action")]
    p = yaml.safe_load(emit_data_text(
        "node-scenarios", "krknctl", recs, {"ACTION": "Act."}, "r"))["params"][0]
    assert p["name"] == "ACTION"
    assert p["flag"] == "action"


def test_krkn_hub_rows_carry_no_flag():
    """env.sh params have no CLI flag and must not gain an empty key."""
    recs = [ParamRecord(name="ACTION", flag="action")]
    p = yaml.safe_load(emit_data_text(
        "node-scenarios", "krkn-hub", recs, {"ACTION": "Act."}, "r"))["params"][0]
    assert "flag" not in p


def test_a_flag_identical_to_the_name_is_not_duplicated():
    """globals.build_groups swaps the flag into name via dataclasses.replace,
    which preserves flag, so all 78 krknctl global rows have name == flag and
    would otherwise gain a key holding the same string."""
    recs = [ParamRecord(name="action", flag="action")]
    p = yaml.safe_load(emit_data_text(
        "globals", "krknctl", recs, {"action": "Act."}, "r"))["params"][0]
    assert "flag" not in p
```

- [ ] **Step 2: Run and watch them fail**

Run: `python -m pytest tests/test_emitter.py -q -k flag`
Expected: the first FAILs with `KeyError: 'flag'`. The third **passes already**, since nothing emits `flag` yet. It is a regression guard against step 3 over-reaching, not a red-to-green test. Do not treat it as a broken run.

- [ ] **Step 3: Implement**

In `_param_dict`, in the existing `if source == "krknctl":` block, above the `allowed_values` line:

```python
    if source == "krknctl":
        # The page lists CLI flags, but name stays the env var: it is the join
        # key to env.sh and what drift_scanner and build_skip_list match on.
        # globals.build_groups has already swapped the flag into name and left
        # flag set, so emitting both there would duplicate a key on every row.
        if rec.flag and rec.flag != rec.name:
            d["flag"] = rec.flag
        if rec.allowed_values:
```

- [ ] **Step 4: Run and watch them pass**

Run: `python -m pytest tests/test_emitter.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bot/emitter.py tests/test_emitter.py
git commit -s -m "Carry the CLI flag on krknctl rows"
```

---

### Task 2: Read the secret marker

**Files:**
- Modify: `bot/parser.py` (`ParamRecord`, `extract_krknctl_params`), `bot/emitter.py`
- Test: `tests/test_parser.py`, `tests/test_emitter.py`

- [ ] **Step 1: Confirm the field shape before writing the test**

```bash
grep -h '"secret"' /c/Users/nayus/Desktop/LFX/krkn_Sync/krkn-hub/*/krknctl-input.json | sort -u
```

Expected: `"secret": "true"` — the **string**, not a boolean. That is why `_as_bool` is needed rather than a truthiness check. 26 entries, 13 distinct names, across `node-scenarios` (11), `power-outages` (11), `zone-outages` (3) and `dummy-scenario` (1), plus one global (`TRIGGER_HTTP_BEARER_TOKEN`).

- [ ] **Step 2: Write the failing test**

```python
def test_a_secret_krknctl_param_is_marked(tmp_path):
    """A reader needs to know not to put the value on a command line. The field
    is the string "true", so a truthiness check would also accept "false"."""
    f = tmp_path / "krknctl-input.json"
    f.write_text(json.dumps([
        {"name": "bmc-password", "variable": "BMC_PASSWORD",
         "type": "string", "secret": "true"},
        {"name": "not-secret", "variable": "NOT_SECRET",
         "type": "string", "secret": "false"},
        {"name": "label-selector", "variable": "LABEL_SELECTOR", "type": "string"},
    ]), encoding="utf-8")
    recs = {r.name: r for r in extract_krknctl_params(f)}
    assert recs["BMC_PASSWORD"].secret is True
    assert recs["NOT_SECRET"].secret is False
    assert recs["LABEL_SELECTOR"].secret is False
```

- [ ] **Step 3: Run and watch it fail**

Run: `python -m pytest tests/test_parser.py -q -k secret`
Expected: FAIL, `TypeError: ParamRecord.__init__() got an unexpected keyword argument 'secret'` if you write the parser first, or `AttributeError: 'ParamRecord' object has no attribute 'secret'` if you do not.

- [ ] **Step 4: Implement**

`bot/parser.py`, add the field to `ParamRecord` below `flag`:

```python
    flag: str | None = None   # krknctl CLI flag, e.g. cerberus-enabled
    secret: bool = False      # krknctl "secret", keep the value off a command line
```

In `extract_krknctl_params`, add to the `records.append(ParamRecord(...))` call:

```python
            secret=_as_bool(item.get("secret", "false")),
```

`bot/emitter.py`, in the `if source == "krknctl":` block:

```python
        if rec.secret:
            d["secret"] = True
```

Emit only when true, so no row gains a `secret: false` key it does not need.

- [ ] **Step 5: Run and watch it pass**

Run: `python -m pytest tests/test_parser.py tests/test_emitter.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add bot/parser.py bot/emitter.py tests/test_parser.py tests/test_emitter.py
git commit -s -m "Read the krknctl secret marker"
```

---

### Task 3: Borrow type from krknctl for the krkn-hub tab

**Files:**
- Modify: `bot/doc_bot.py` (`_krknctl_desc_map` and the loop in `run()`)
- Test: `tests/test_doc_bot.py`

`env.sh` carries no type information, so 34 published rows lose their Type cell. `run()` already joins env params to their krknctl counterparts to borrow descriptions. This extends that join rather than adding a second one, and covers 30 of the 34. The other 4 have no krknctl counterpart and are handled in Task 8.

- [ ] **Step 1: Write the failing test**

```python
def test_env_params_borrow_type_from_krknctl(tmp_path):
    """env.sh has no types. The join that already borrows descriptions carries
    the type too. The second param proves the description-only filter is gone:
    a krknctl entry with a type and no description must still give its type."""
    hub = tmp_path / "hub" / "node-scenarios"
    hub.mkdir(parents=True)
    (hub / "env.sh").write_text(
        'export TIMEOUT=${TIMEOUT:=180}\nexport RUNS=${RUNS:=1}\n', encoding="utf-8")
    (hub / "krknctl-input.json").write_text(json.dumps([
        {"name": "timeout", "variable": "TIMEOUT", "type": "number",
         "description": "How long to wait"},
        {"name": "runs", "variable": "RUNS", "type": "number"},
    ]), encoding="utf-8")
    web = tmp_path / "web"
    run("node-scenarios", tmp_path / "hub", web, tmp_path / "no-krkn")
    rows = {r["name"]: r for r in yaml.safe_load(
        (web / "data/params/node-scenarios/krkn-hub.yaml").read_text(encoding="utf-8"))["params"]}
    assert rows["TIMEOUT"]["type"] == "number"
    assert rows["TIMEOUT"]["description"] == "How long to wait"
    assert rows["RUNS"]["type"] == "number"
```

- [ ] **Step 2: Run and watch it fail**

Run: `python -m pytest tests/test_doc_bot.py -q -k borrow_type`
Expected: FAIL, `KeyError: 'type'`

- [ ] **Step 3: Implement**

Rename the helper, since it stops being description-only, and drop its filter:

```python
def _krknctl_records(scn):
    """Param name -> the krknctl record, used to fill env.sh params that carry
    no description or type of their own. env.sh has no type information at all,
    so an entry with a type and no description still has something to give."""
    f = scn / "krknctl-input.json"
    if not f.exists():
        return {}
    return {r.name: r for r in extract_krknctl_params(f)}
```

In `run()`, replace the description-only loop:

```python
            kctl = _krknctl_records(scn)
            for r in recs:
                match = kctl.get(r.name)
                if match is None:
                    continue
                if not r.description and match.description:
                    r.description = match.description
                    r.description_source = "krknctl"
                if r.type is None:
                    r.type = match.type
```

Setting `description_source` here matches what `globals.build_groups` already does on the same join.

- [ ] **Step 4: Run and watch them pass**

Run: `python -m pytest tests/test_doc_bot.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bot/doc_bot.py tests/test_doc_bot.py
git commit -s -m "Borrow the krknctl type for env.sh params"
```

---

### Task 4: Shortcode renders the flag, the secret marker and the new column order

**Files:**
- Modify: `website-template/layouts/shortcodes/param-table.html`
- Verify: real Hugo render

Four changes in one pass, because they touch the same two blocks and splitting them would mean rendering the site four times. There is no Hugo test in this repo, so this is verified by eye against the real site.

- [ ] **Step 1: Move Possible Values last in the header row**

```html
  <thead>
    <tr>
      <th>Parameter</th>
      <th>Description</th>
      {{- if $showType }}<th>Type</th>{{ end }}
      {{- if $showDefault }}<th>Default</th>{{ end }}
      {{- if $showRequired }}<th>Required</th>{{ end }}
      {{- if $showValues }}<th>Possible Values</th>{{ end }}
    </tr>
  </thead>
```

- [ ] **Step 2: Rewrite the body row to match**

```html
    {{- $hasDefault := isset . "default" -}}
    {{- $d := "" -}}{{- if $hasDefault }}{{ $d = printf "%v" (index . "default") }}{{ end -}}
    <tr>
      {{/* The krknctl pages list CLI flags. name stays the env var in the data
           so the drift scanner and skip list keep matching on it. */}}
      <td><code>{{ $prefix }}{{ if isset . "flag" }}{{ index . "flag" }}{{ else }}{{ index . "name" }}{{ end }}</code></td>
      <td>{{ index . "description" | markdownify }}</td>
      {{- if $showType }}<td>{{ index . "type" | default "-" }}{{ if isset . "secret" }} (secret){{ end }}</td>{{ end }}
      {{/* Long defaults (TELEMETRY_FILTER_PATTERN is a ~250 char regex array)
           would wreck the layout, so show the head and keep the rest on hover. */}}
      {{- if $showDefault }}<td{{ if gt (len $d) 60 }} title="{{ $d }}"{{ end }}>
        {{- if not $hasDefault }}-
        {{- else if eq $d "" }}<code>""</code>
        {{- else if gt (len $d) 60 }}<code>{{ substr $d 0 60 }}...</code>
        {{- else }}<code>{{ $d }}</code>{{ end -}}
      </td>{{ end }}
      {{- if $showRequired }}<td>{{ if isset . "required" }}{{ if index . "required" }}Yes{{ else }}No{{ end }}{{ else }}-{{ end }}</td>{{ end }}
      {{/* Blank, not a dash: two thirds of rows are non-enum and a column of
           dashes reads as noise. Default keeps its dash, where it means
           "no default declared" as opposed to default: "". */}}
      {{- if $showValues }}<td>{{ with index . "possible_values" }}{{ delimit . "/" }}{{ end }}</td>{{ end }}
    </tr>
```

- [ ] **Step 3: Regenerate and render**

```bash
cd /c/Users/nayus/Desktop/LFX/krkn_Sync/website
git checkout bot/docs-sync-121
export PYTHONPATH=/c/Users/nayus/Desktop/LFX/krkn_Sync/krkn-docs-bot-gh-aw/krkn-docs-bot-gh-aw
KRKN_HUB_PATH=../krkn-hub KRKN_PATH=../krkn WEBSITE_ROOT=. \
  python -m bot.doc_bot --scenario node-scenarios
./node_modules/hugo-extended/vendor/hugo.exe --logLevel warn --destination public-test
```

Expected: build succeeds with no errors.

- [ ] **Step 4: Check the rendered krknctl table**

Serve and open `http://localhost:1314/docs/scenarios/node-scenarios/`. Confirm:
- Parameter column shows `action`, not `ACTION`
- `bmc-password` type reads `string (secret)`
- Possible Values is the last column
- Non-enum rows have an empty Possible Values cell, not a dash
- Required reads Yes / No
- `EXCLUDE_LABEL` default still renders `""` and `INTERFACE` still renders `-`

Two things to expect rather than treat as failures. The flag has **no leading `--` yet**: that arrives in Task 5, and only on tab files written after it, since the shortcode calls already committed on this branch carry no `prefix` argument. And a secret param with no `type` renders `- (secret)`, because the Type column is only shown when some row in the table has a type.

The last bullet is the regression guard for the empty-versus-missing default fix that shipped in `e9dc316`. If `EXCLUDE_LABEL` and `INTERFACE` both show a dash, step 2 was applied wrong.

- [ ] **Step 5: Commit**

```bash
git add website-template/layouts/shortcodes/param-table.html
git commit -s -m "Render CLI flags, mark secrets, and reorder the columns"
```

---

### Task 5: Pass the flag prefix on the per-scenario tabs

**Files:**
- Modify: `bot/scaffold.py` (`inject_shortcode`, `scaffold_scenario`)
- Test: `tests/test_scaffold.py` (including **updating an existing assertion**)

`inject_global_shortcodes` already does this for the global pages. The two per-scenario call sites do not.

- [ ] **Step 1: Write the failing tests**

`TAB` at `tests/test_scaffold.py:83` is the existing one-table page fixture. Reuse it.

```python
def test_the_krknctl_tab_call_carries_the_flag_prefix():
    """The source stores a bare flag name but a reader types --telemetry-enabled."""
    out = inject_shortcode(TAB, "node-scenarios", "krknctl")
    assert 'prefix="--"' in out


def test_the_krkn_hub_tab_call_does_not():
    """env.sh params are env vars and take no prefix."""
    out = inject_shortcode(TAB, "node-scenarios", "krkn-hub")
    assert "prefix" not in out
```

- [ ] **Step 2: Run and watch them fail**

Run: `python -m pytest tests/test_scaffold.py -q -k prefix`
Expected: FAIL on the first assertion

- [ ] **Step 3: Implement, and fix the assertion this breaks**

Add a helper above `inject_shortcode` and use it at both call sites:

```python
def _call(scenario, source):
    # krkn-hub params are env vars and take no prefix.
    prefix = ' prefix="--"' if source == "krknctl" else ""
    return f'{{{{< param-table scenario="{scenario}" source="{source}"{prefix} >}}}}'
```

In `inject_shortcode`, replace the `call = ...` line with `call = _call(scenario, source)`. In `scaffold_scenario`, replace the stub-tab write with `tab.write_text(_call(scenario, source) + "\n", encoding="utf-8")`.

**`tests/test_scaffold.py:68` asserts the old string** and will fail:

```python
assert '{{< param-table scenario="brand-new-scenario" source="krknctl" >}}' in krknctl_tab
```

Update it to include ` prefix="--"`. It is the only existing krknctl assertion of this shape; the `inject_shortcode` tests all use `krkn-hub` and are unaffected.

`inject_global_shortcodes` keeps its own inline version, because it also needs `group=`. Leave it alone.

- [ ] **Step 4: Run and watch them pass**

Run: `python -m pytest -q`
Expected: PASS. One existing assertion was edited, so the count is 124 plus the new tests, not 126 plus.

- [ ] **Step 5: Commit**

```bash
git add bot/scaffold.py tests/test_scaffold.py
git commit -s -m "Pass the flag prefix on the per-scenario krknctl tab"
```

---

## Chunk 2: Never lose a cell

### Task 6: Read a published markdown table

**Files:**
- Modify: `bot/scaffold.py` (`_first_cell`)
- Test: `tests/test_scaffold.py`

`_first_cell` already splits a row and strips the formatting off cell one. This generalises it rather than adding a second parser.

It reads **every** table on the page, not the first. The two global pages carry one table per group, so a first-table-only scan would see one group and blank the other ten. `_tables()` already returns every table (verified shape: `(header_index, end_index, row_indexes)`), because `inject_global_shortcodes` needed exactly that.

- [ ] **Step 1: Write the failing tests**

```python
PUBLISHED = """\
Parameter | Description | Type | Default
--------- | ----------- | ---- | -------
ACTION    | Do a thing  | enum | stop
TIMEOUT   |             | number | 180
"""

SECOND_GROUP = """\
Parameter | Description | Default
--------- | ----------- | -------
SIGNAL_STATE | Waits for the RUN signal | RUN
"""


def test_published_table_keys_rows_on_the_parameter():
    """Headers travel with each row, since two tables on one page can differ."""
    rows = published_table(PUBLISHED)
    assert set(rows) == {"ACTION", "TIMEOUT"}
    headers, cells = rows["ACTION"]
    assert headers == ["parameter", "description", "type", "default"]
    assert cells[1] == "Do a thing"


def test_published_table_reads_every_table_on_the_page():
    """The global pages carry one table per group. A first-table-only scan
    would blank every group but one."""
    rows = published_table(PUBLISHED + "\n" + SECOND_GROUP)
    assert set(rows) == {"ACTION", "TIMEOUT", "SIGNAL_STATE"}
    assert published_cell(rows, "SIGNAL_STATE", "description") == "Waits for the RUN signal"


def test_published_cell_on_a_column_the_table_does_not_have():
    """The global pages have no Type column at all."""
    rows = published_table(SECOND_GROUP)
    assert published_cell(rows, "SIGNAL_STATE", "type") == ""


def test_published_table_strips_the_flag_prefix():
    """The krknctl page lists --action; the data file keys name on ACTION."""
    rows = published_table("Parameter | Description\n--- | ---\n`--action` | Do it\n")
    assert set(rows) == {"action"}


def test_published_table_on_a_page_with_no_table():
    assert published_table("just prose\n") == {}
```

- [ ] **Step 2: Run and watch them fail**

Run: `python -m pytest tests/test_scaffold.py -q -k published`
Expected: FAIL at collection with `ImportError: cannot import name 'published_table' from 'bot.scaffold'`, because `tests/test_scaffold.py:1` imports symbols explicitly. Add the names to that import line as you go.

- [ ] **Step 3: Implement**

```python
def _row_cells(line):
    """Cells of a markdown table row, formatting stripped. Handles both page
    styles: "| `--flag` | ... |" on the krknctl page and "`NAME` | ... " with no
    outer pipes on the krkn-hub page."""
    return [c.strip().strip("`").strip() for c in line.strip().strip("|").split("|")]


def _first_cell(line):
    """Parameter name from a table row, or None. A CLI flag's leading -- is
    stripped so it matches the flag stored in the data file."""
    cells = _row_cells(line)
    if not cells:
        return None
    cell = cells[0]
    if cell.startswith("--"):
        cell = cell[2:]
    return cell or None


def published_table(text):
    """{parameter: (lowercased headers, cells)} for every table on the page.

    Every table, not just the first: the global pages carry one per group. The
    headers travel with each row because two tables on one page need not have
    the same columns. First occurrence of a parameter wins.
    """
    lines = text.splitlines()
    out = {}
    for header, _end, row_indexes in _tables(lines):
        headers = [h.lower() for h in _row_cells(lines[header])]
        for i in row_indexes:
            name = _first_cell(lines[i])
            if name and name not in out:
                out[name] = (headers, _row_cells(lines[i]))
    return out


def published_cell(rows, name, column):
    """The cell under `column` for `name`, or "" when the row or the column is
    not there. The global pages have no Type column, so a miss is normal."""
    headers, cells = rows.get(name, ([], []))
    i = headers.index(column) if column in headers else -1
    return cells[i] if 0 <= i < len(cells) else ""
```

- [ ] **Step 4: Run and watch them pass**

Run: `python -m pytest tests/test_scaffold.py -q`
Expected: PASS. The existing `inject_global_shortcodes` tests must still pass, since `_first_cell` behaviour is unchanged.

- [ ] **Step 5: Commit**

```bash
git add bot/scaffold.py tests/test_scaffold.py
git commit -s -m "Read the whole published table, not just the parameter column"
```

---

### Task 7: Make type and provenance survive regeneration

**Files:**
- Modify: `bot/emitter.py` (`_param_dict`, `load_descriptions`)
- Test: `tests/test_emitter.py`

**This task exists because of a bug that would otherwise make Task 8 pointless.** The published table is destroyed by the same run that reads it: `scaffold_scenario` replaces it with the shortcode call. So anything Task 8 carries has to be picked up by the existing-file rung on the next run, and today that rung returns descriptions only. A type carried on run 1 would render `-` on run 2, and `description_source` is never written at all, so the provenance guarantee would last exactly one commit.

- [ ] **Step 1: Write the failing tests**

```python
def test_provenance_is_written_to_the_data_file():
    recs = [ParamRecord(name="X", description_source="published-table")]
    p = yaml.safe_load(emit_data_text(
        "s", "krkn-hub", recs, {"X": "Text."}, "r"))["params"][0]
    assert p["description_source"] == "published-table"


def test_a_record_with_no_provenance_gains_no_key():
    recs = [ParamRecord(name="X")]
    p = yaml.safe_load(emit_data_text(
        "s", "krkn-hub", recs, {"X": "Text."}, "r"))["params"][0]
    assert "description_source" not in p


def test_the_read_back_returns_type_and_provenance(tmp_path):
    """The published table is gone by run 2, so whatever it supplied has to
    come back from the file or it lasted one commit."""
    f = tmp_path / "krkn-hub.yaml"
    f.write_text(
        "params:\n"
        "  - name: VERIFY_SESSION\n"
        "    description: Verify the SSH session\n"
        "    type: string\n"
        "    description_source: published-table\n", encoding="utf-8")
    prev = load_previous(f)
    assert prev["VERIFY_SESSION"]["description"] == "Verify the SSH session"
    assert prev["VERIFY_SESSION"]["type"] == "string"
    assert prev["VERIFY_SESSION"]["description_source"] == "published-table"


def test_the_read_back_on_a_missing_file(tmp_path):
    assert load_previous(tmp_path / "nope.yaml") == {}
```

- [ ] **Step 2: Run and watch them fail**

Run: `python -m pytest tests/test_emitter.py -q -k "provenance or read_back"`
Expected: FAIL at collection with `ImportError: cannot import name 'load_previous'`.

- [ ] **Step 3: Implement**

In `_param_dict`, after the `description` key:

```python
    # Provenance travels in the data so a later run can tell a carried or
    # generated description from a maintainer's, and so one grep finds them all.
    if rec.description_source:
        d["description_source"] = rec.description_source
```

Add alongside `load_descriptions`, keeping the old function so nothing else breaks:

```python
def load_previous(path):
    """name -> the whole previous row. load_descriptions returns descriptions
    only, which is enough for its callers but loses the type and the provenance
    that the published-table rung supplies exactly once."""
    path = Path(path)
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {p["name"]: p for p in data.get("params", [])}
```

- [ ] **Step 4: Run and watch them pass**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bot/emitter.py tests/test_emitter.py
git commit -s -m "Write and read back type and description provenance"
```

---

### Task 8: Carry description and type forward from the published table

**Files:**
- Modify: `bot/descriptions.py`, `bot/doc_bot.py`, `bot/globals.py`
- Test: `tests/test_description_resolution.py`, `tests/test_doc_bot.py`, `tests/test_globals.py`

This is the rung that stops the 4 blanks and fills the Type cells krknctl cannot supply. `default` is deliberately **not** carried: `env.sh` is authoritative and a disagreement there is the drift signal the bot exists to raise.

- [ ] **Step 1: Write the failing tests for the chain**

```python
def test_a_published_description_is_carried_when_no_source_has_one():
    """node-scenarios/VERIFY_SESSION today: the page has wording, no source does."""
    recs = [ParamRecord(name="VERIFY_SESSION")]
    descs, gaps = resolve_descriptions(
        "node-scenarios", recs, {}, _no_descriptions,
        published={"VERIFY_SESSION": "Verify the SSH session"})
    assert descs["VERIFY_SESSION"] == "Verify the SSH session"
    assert recs[0].description_source == "published-table"
    assert gaps == [("VERIFY_SESSION", "published-table", "Verify the SSH session")]


def test_a_source_description_still_wins_over_the_published_one():
    """CLOUD_TYPE's published list omits azure and gcp. The source is right."""
    recs = [ParamRecord(name="CLOUD_TYPE", description="aws, azure, gcp")]
    descs, gaps = resolve_descriptions(
        "s", recs, {}, _no_descriptions, published={"CLOUD_TYPE": "aws, vmware"})
    assert descs["CLOUD_TYPE"] == "aws, azure, gcp"
    assert gaps == []


def test_the_existing_file_still_wins_over_the_published_one():
    recs = [ParamRecord(name="X")]
    descs, _ = resolve_descriptions(
        "s", recs, {"X": "from yaml"}, _no_descriptions, published={"X": "from page"})
    assert descs["X"] == "from yaml"


def test_a_blank_with_nothing_anywhere_is_reported():
    recs = [ParamRecord(name="NEW")]
    descs, gaps = resolve_descriptions("s", recs, {}, _no_descriptions)
    assert descs["NEW"] == ""
    assert gaps == [("NEW", "", "no description in any source and no published row")]
```

`_no_descriptions` is the existing no-op shape used in `doc_bot.py` and `globals.py`; the test module already defines equivalents (`fake_llm` and an inline `lambda s, n: {}`). Reuse whichever is there.

- [ ] **Step 2: Run and watch them fail**

Run: `python -m pytest tests/test_description_resolution.py -q`
Expected: FAIL, `TypeError: resolve_descriptions() got an unexpected keyword argument 'published'`

- [ ] **Step 3: Implement the chain**

```python
def resolve_descriptions(scenario, records, existing, llm_fn, published=None):
    """Return (descriptions_by_name, gaps).

    Priority: source -> existing file -> published table -> llm_fn.

    The old order put existing first, to protect hand-edits. But the file it
    protected is stamped "Do not edit by hand", so all it did was freeze wording
    at first generation. Every other field already takes the source as truth.

    published is the hand-written table the shortcode is about to replace. It is
    the last place a curated description survives, so it is read before giving
    up. Only description and type are carried: default comes from env.sh alone,
    and a published default that disagrees is drift, not a fallback.

    gaps lists every name whose text did not come from a source file, as
    (name, filled_from, text). filled_from is "published-table", "llm", or ""
    when nothing produced anything, in which case text is the reason.
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
                gaps.append((name, "", "no description in any source "
                                       "and no published row"))
    return out, gaps
```

- [ ] **Step 4: Wire it into `doc_bot._emit_one`**

Two joins to get right here, both of which an earlier draft got wrong.

```python
def _published(website_root, scenario, source):
    """description and type cells from the hand-written table the shortcode is
    about to replace, keyed by the identifier the published page uses."""
    from bot.scaffold import _find_tab, published_table, published_cell
    tab = _find_tab(website_root, scenario, source)
    if tab is None:
        return {}, {}
    rows = published_table(tab.read_text(encoding="utf-8"))
    def col(c):
        return {k: published_cell(rows, k, c) for k in rows
                if published_cell(rows, k, c)}
    return col("description"), col("type")
```

**Use `_find_tab`, not a path built from the scenario name.** Website page directories diverge from source scenario names: `hog-scenarios/cpu-hog-scenario` is the page for `node-cpu-hog`, and `network-chaos-ng-scenarios/node-interface-down`, `node-scenarios/node-scenarios-bm`, `kubevirt-vm-outage-scenario`, `power-outage-scenarios` and `zone-outage-scenarios` all diverge too. Only 12 of the 31 match by name. `_find_tab` resolves the rest through the `<krkn-hub-scenario id="...">` marker and is already regression-tested at `tests/test_scaffold.py:29-45`.

```python
def _emit_one(scenario, source, records, website_root, source_ref):
    out = website_root / "data" / "params" / scenario / f"{source}.yaml"
    prev = load_previous(out)
    pub_desc, pub_type = _published(website_root, scenario, source)
    for r in records:
        # The krknctl page lists --action while the record is keyed ACTION, so
        # the published table is keyed by flag and the record by env var.
        key = r.flag or r.name
        if r.type is None:
            r.type = prev.get(r.name, {}).get("type") or pub_type.get(key) or None
        if not r.description_source:
            r.description_source = prev.get(r.name, {}).get("description_source")
    published = {r.name: pub_desc[r.flag or r.name] for r in records
                 if (r.flag or r.name) in pub_desc}
    existing = {n: p.get("description", "") for n, p in prev.items()}
    descs, gaps = resolve_descriptions(scenario, records, existing,
                                       _no_descriptions, published=published)
    emit_data_file(website_root, scenario, source, records, descs, source_ref)
    return [(scenario, source) + g for g in gaps]
```

The `published` dict is re-keyed by `r.name` before the call, because `resolve_descriptions` looks up `r.name`. Without that line the whole rung is dead on the krknctl source. This is currently masked: all 278 per-scenario krknctl params already have a description and a type, so a test on that source passes either way.

`run()` returns the concatenated gaps from both sources.

- [ ] **Step 5: Write the failing test for the globals path**

Six krkn-hub global params have no description in any source and at least three have curated text on the published page. `tests/test_globals.py` already has a sources fixture; add `export SIGNAL_STATE=${SIGNAL_STATE:=RUN}` to its `env.sh` rather than pointing at the real checkouts.

```python
def test_a_global_description_is_carried_from_the_published_page(tmp_path, sources):
    """globals.emit() forks the emit path, so it needs the rung wired
    separately. SIGNAL_STATE has a long page description and none in any source."""
    web = tmp_path / "web"
    page = web / "content/en/docs/scenarios"
    page.mkdir(parents=True)
    (page / "all-scenario-env.md").write_text(
        "Parameter | Description | Default\n"
        "--------- | ----------- | -------\n"
        "`SIGNAL_STATE` | Waits for the RUN signal | RUN\n", encoding="utf-8")
    g.emit(web, sources.hub, sources.krkn)
    rows = {r["name"]: r for r in yaml.safe_load(
        (web / "data/params/globals/krkn-hub.yaml").read_text(encoding="utf-8"))["params"]}
    assert rows["SIGNAL_STATE"]["description"] == "Waits for the RUN signal"
```

- [ ] **Step 6: Wire it into `globals.emit`**

```python
def _published_globals(website_root):
    """{source: {param: description}} from the two global pages. They carry one
    table per group, which published_table already handles."""
    from bot.scaffold import published_table, published_cell
    out = {}
    for source, rel in _PAGES:
        page = Path(website_root) / rel
        rows = published_table(page.read_text(encoding="utf-8")) if page.exists() else {}
        out[source] = {k: published_cell(rows, k, "description") for k in rows
                       if published_cell(rows, k, "description")}
    return out
```

Build it once above the loop in `emit()` and pass `published=pub[source]`.

The import can be module-level: `bot/scaffold.py` imports only stdlib and deliberately keeps `GLOBAL_SCENARIO` local so it never imports `bot.globals`, so there is no cycle. Function-local is fine too, matching `globals.scaffold`; just do not claim a cycle that does not exist.

Type is not carried here. All 75 krkn-hub global records lack one, but the published page is `Parameter | Description | Default` with no Type column, so there is nothing to carry.

- [ ] **Step 7: Write the two-run test**

This is the one that proves Task 7 was needed.

```python
def test_a_carried_type_and_marker_survive_the_next_run(tmp_path):
    """Run 1 reads the published table and the shortcode replaces it. Run 2 has
    no table, so both have to come back from the data file."""
    ...  # emit, assert type and description_source, delete the tab, emit again
    assert rows["VERIFY_SESSION"]["type"] == "string"
    assert rows["VERIFY_SESSION"]["description_source"] == "published-table"
```

- [ ] **Step 8: Run the whole suite**

Run: `python -m pytest -q`
Expected: PASS. `globals.py`'s `descs, _ =` still works because only the *shape* of the second element changed, not the arity.

- [ ] **Step 9: Commit**

```bash
git add bot/descriptions.py bot/doc_bot.py bot/globals.py tests/
git commit -s -m "Carry a description and type forward from the published table"
```

---

### Task 9: Build the commit-message report

**Files:**
- Create: `bot/report.py`
- Modify: `bot/doc_bot.py` (`main`)
- Test: `tests/test_report.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_a_pipe_in_generated_text_cannot_add_a_column():
    """One description containing | silently adds a column and shifts the row.
    Count unescaped pipes: an escaped \\| still contains a pipe character."""
    md = render([("s", "krkn-hub", "P", "llm", "takes a|b|c")], [], [])
    row = [l for l in md.splitlines() if l.startswith("| s ")][0]
    assert row.count("|") - row.count(r"\|") == 5   # 4 columns plus trailing
    assert r"\|" in row


def test_a_newline_in_generated_text_cannot_break_the_row():
    md = render([("s", "krkn-hub", "P", "llm", "first line\nsecond line")], [], [])
    assert "first line second line" in md


def test_blank_params_get_their_own_section_with_a_reason():
    md = render([], [("s", "krkn-hub", "P", "no description produced")], [])
    assert "### Still blank (1)" in md
    assert "no description produced" in md


def test_a_clean_run_renders_nothing():
    """No sections at all, so a normal commit message stays normal."""
    assert render([], [], []) == ""
```

- [ ] **Step 2: Run and watch them fail**

Run: `python -m pytest tests/test_report.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'bot.report'`

- [ ] **Step 3: Implement**

```python
import re

_FIX_HINT = """\
These render as an empty cell. Fix by adding a trailing comment in env.sh:
  export BLOCK_SIZE=${BLOCK_SIZE:=1024}   # Size of each written block
"""


def _cell(text):
    """Table cell. A newline or a pipe in generated text would break the row."""
    return re.sub(r"\s+", " ", text or "").replace("|", r"\|").strip()


def render(filled, blank, orphans):
    """Commit-message sections for descriptions that did not come from source.

    filled is (scenario, source, param, filled_from, text); blank is
    (scenario, source, param, reason); orphans is (scenario, source, param) for
    rows on the published page that no source produces. All sorted here so the
    same run always produces the same bytes. Empty sections are omitted.
    """
    out = []
    if filled:
        out += [f"### Descriptions not taken from source ({len(filled)})\n",
                "| Scenario | Parameter | Filled from | Text |",
                "| --- | --- | --- | --- |"]
        out += [f"| {s} | {p} | {src} | {_cell(t)} |"
                for s, _sr, p, src, t in sorted(filled)]
        out.append("")
    if blank:
        out += [f"### Still blank ({len(blank)})\n",
                "| Scenario | Parameter | Why |", "| --- | --- | --- |"]
        out += [f"| {s} | {p} | {_cell(why)} |" for s, _sr, p, why in sorted(blank)]
        out += ["", _FIX_HINT]
    if orphans:
        out += [f"### Dropped, not in any source ({len(orphans)})\n",
                "| Scenario | Source | Parameter |", "| --- | --- | --- |"]
        out += [f"| {s} | {sr} | {p} |" for s, sr, p in sorted(orphans)]
        out.append("")
    return "\n".join(out)
```

- [ ] **Step 4: Append, do not overwrite**

`doc_bot.main()` handles **one** scenario. The loop is in the workflow shell, which invokes the module once per target with the same report directory, so a plain write means the last target erases the rest.

```python
    report_dir = os.environ.get("GH_AW_REPORT_DIR")
    if report_dir:
        p = Path(report_dir, "gaps.md")
        with p.open("a", encoding="utf-8") as fh:
            fh.write(render(filled, blank, orphans))
```

`filled`, `blank` and `orphans` are partitioned from the gap tuples `run()` returns, which are `(scenario, source, name, filled_from, text)`.

- [ ] **Step 5: Run and watch them pass**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add bot/report.py bot/doc_bot.py tests/test_report.py
git commit -s -m "Report descriptions that did not come from source"
```

---

## Chunk 3: The model rung

### Task 10: Verify the endpoint before writing against it

**Files:** none. This is a five-minute check that decides Task 11's config.

`COPILOT_GITHUB_TOKEN` is issued for Copilot CLI. The chat-completions endpoint may refuse it. Find out before building on it.

- [ ] **Step 1: Try it**

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://api.githubcopilot.com/chat/completions \
  -H "Authorization: Bearer $COPILOT_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Copilot-Integration-Id: vscode-chat" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"say ok"}],"max_tokens":5}'
```

- [ ] **Step 2: Record the outcome**

- `200` -> use it, no new secret, no new allowlist entry, nothing else to configure.
- `401` / `403` -> the token is not valid for this endpoint. Fall back to a dedicated `OPENAI_API_KEY` secret. Nothing else in the design changes; `bot/describe.py` only ever sees a base URL and a key.

Either way, note that custom steps run outside the firewall (lock lines 523-620 versus AWF at 625), so no `network.allowed` change is needed in either case.

---

### Task 11: `bot/describe.py`

**Files:**
- Create: `bot/describe.py`
- Test: `tests/test_describe.py`

The model never touches a file. It returns strings, Python validates them, and Python writes. There is nothing to contain, which is why this exists instead of letting the agent edit YAML.

- [ ] **Step 1: Write the failing tests**

Every test uses a fake transport. Never a live endpoint.

```python
def test_a_good_response_is_returned():
    t = fake({"choices": [{"message": {"content":
        '{"BLOCK_SIZE": "Size in bytes of each block written to the volume"}'}}]})
    assert describe("pvc-scenario", ["BLOCK_SIZE"], CTX, transport=t) == {
        "BLOCK_SIZE": "Size in bytes of each block written to the volume"}


def test_a_non_200_returns_nothing():
    """A blank cell is already legal and already reported. A failed call must
    never fail the run, or one flaky box takes the whole sync down."""
    assert describe("s", ["X"], CTX, transport=fake(status=500)) == {}


def test_malformed_json_returns_nothing():
    t = fake({"choices": [{"message": {"content": "here you go: not json"}}]})
    assert describe("s", ["X"], CTX, transport=t) == {}


def test_a_timeout_returns_nothing():
    assert describe("s", ["X"], CTX, transport=raises(TimeoutError)) == {}


def test_a_name_that_was_not_asked_for_is_dropped():
    t = fake({"choices": [{"message": {"content":
        '{"X": "fine", "MADE_UP": "not asked for"}'}}]})
    assert set(describe("s", ["X"], CTX, transport=t)) == {"X"}


def test_text_that_invents_a_value_is_rejected():
    """A model that writes "default 1024" when the source says 512 produces
    something that reads as authoritative and is wrong, which is worse than an
    empty cell."""
    rec = {"name": "BLOCK_SIZE", "default": "512"}
    assert validate("Block size, default 1024", rec) == \
        'rejected: contains a value not in the source ("1024")'


def test_a_value_that_is_in_the_source_is_accepted():
    assert validate("Block size in bytes, defaults to 512", 
                    {"name": "BLOCK_SIZE", "default": "512"}) is None


def test_text_over_the_length_limit_is_rejected():
    assert "too long" in validate("x" * 121, {"name": "X"})


def test_a_placeholder_is_rejected():
    assert validate("Configures port.", {"name": "PORT"}) == "rejected: says nothing"
```

- [ ] **Step 2: Run and watch them fail**

Run: `python -m pytest tests/test_describe.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'bot.describe'`

- [ ] **Step 3: Implement**

```python
import json
import os
import re

MAX_LEN = 120
_NUMBER_OR_QUOTED = re.compile(r'"[^"]+"|\b\d+\b')
_PLACEHOLDER = re.compile(r'^(configures?|sets?|specifies|controls?) (the )?\w+\.?$', re.I)

_PROMPT = """\
Write one plain sentence describing each parameter, for a documentation table.

Rules:
- One sentence, at most 120 characters, no markdown, no trailing period needed.
- Describe only what the context below already states.
- Never state a default, a range or a unit that is not in that parameter's own
  record. If unsure, return an empty string for that parameter.
- Match the voice of the examples.

Return JSON only: an object mapping each parameter name to its sentence.
"""


def validate(text, record):
    """None if the text is usable, otherwise the reason it is not."""
    text = (text or "").strip()
    if not text:
        return "no description produced"
    if "\n" in text:
        return "rejected: contains a newline"
    if len(text) > MAX_LEN:
        return f"rejected: too long ({len(text)} > {MAX_LEN})"
    if _PLACEHOLDER.match(text):
        return "rejected: says nothing"
    known = " ".join(str(v) for v in record.values())
    for lit in _NUMBER_OR_QUOTED.findall(text):
        if lit.strip('"') not in known:
            return f'rejected: contains a value not in the source ("{lit.strip(chr(34))}")'
    return None
```

Note the quoting in that last message: `_NUMBER_OR_QUOTED` matches a bare `1024` with no quotes, so the f-string has to add them or the test above fails.

```python
def describe(scenario, names, ctx, transport=None):
    """{name: sentence} for the names that produced usable text.

    Returns {} on any failure: non-200, malformed JSON, timeout, endpoint
    unreachable, missing credentials. A blank cell is already a legal outcome
    and is already reported, so a failed call never fails the run.
    """
    base = os.environ.get("OPENAI_BASE_URL")
    key = os.environ.get("OPENAI_API_KEY")
    if not (base and key) and transport is None:
        return {}
    try:
        body = _post(transport, base, key, _PROMPT, ctx, names)
        raw = json.loads(body["choices"][0]["message"]["content"])
    except Exception:
        return {}
    return {n: raw[n] for n in names
            if isinstance(raw.get(n), str) and raw[n].strip()}
```

Validation is applied by the caller in Task 12, so the reasons can reach the report.

- [ ] **Step 4: Run and watch them pass**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bot/describe.py tests/test_describe.py
git commit -s -m "Add the model description rung, failing soft"
```

---

### Task 12: Wire the model rung into the chain and the workflow

**Files:**
- Modify: `bot/doc_bot.py`, `.github/workflows/doc-sync.md`
- Test: `tests/test_doc_bot.py`

- [ ] **Step 1: Replace `_no_descriptions` with a real caller**

```python
def _describe(scn, records):
    """llm_fn for resolve_descriptions. Assembles context deterministically,
    calls the model, validates, and drops anything that fails."""
    def fn(scenario, names):
        by_name = {r.name: r for r in records}
        ctx = _context(scn, [by_name[n] for n in names], records)
        out = {}
        for name, text in describe(scenario, names, ctx).items():
            if validate(text, asdict(by_name[name])) is None:
                out[name] = text
        return out
    return fn
```

`_context` gives the model the scenario README, each parameter's own `env.sh` line and krknctl entry, and up to five real descriptions from the same scenario as style examples. The examples are the part the agent route could not do: they keep the sentence in the house voice.

- [ ] **Step 2: Pass the endpoint through in the workflow**

In the existing "Generate parameter data and scaffold" step, add to `env:`:

```yaml
      OPENAI_BASE_URL: https://api.githubcopilot.com
      OPENAI_API_KEY: ${{ secrets.COPILOT_GITHUB_TOKEN }}
      GH_AW_REPORT_DIR: ${{ runner.temp }}
```

Substitute whatever Task 10 established. **The agent block does not change**: no new prompt text, `max-turns` stays 3, no file-editing grant, no new safe output.

- [ ] **Step 3: Append the report to the commit message**

Keep the existing heredoc verbatim, redirect it to a file, then append:

```bash
      cat > "$RUNNER_TEMP/commit-msg.txt" <<COMMIT_MSG
      ...exactly as today...
      COMMIT_MSG
      # Bot-written and may contain model-authored text, so it is appended as a
      # file and never becomes shell source. A ${{ }} expression would be
      # substituted into the script before bash parses it, which is the actual
      # injection point here; a heredoc body is not.
      cat "$RUNNER_TEMP/gaps.md" >> "$RUNNER_TEMP/commit-msg.txt" 2>/dev/null || true
      git commit -s -F "$RUNNER_TEMP/commit-msg.txt" || echo "no changes to commit"
```

The commit step stays where it is, in `steps:`. It must not move to `post-steps`: those compile **after** `Ingest agent output` (probe: pre-step 427, agent 744, `collect_output` 873, post-steps 950), and the PR is built from the patch collected there, so a post-step commit would never reach it.

- [ ] **Step 4: Compile**

Ask the user to run it; the compile needs their terminal.

```bash
gh aw compile doc-sync
```

Expected: 0 errors. The known `bots:` plus `slash_command` warning stays, as do the shell-injection extraction warnings on `${{ steps.scn.outputs.scenarios }}`.

- [ ] **Step 5: Commit**

```bash
git add bot/doc_bot.py .github/workflows/doc-sync.md tests/test_doc_bot.py
git commit -s -m "Call the model for descriptions no source provides"
```

---

## Chunk 4: Verification

### Task 13: Turn the audit into a regression test

**Files:**
- Create: `tests/test_no_regression_audit.py`
- Reference: `docs/superpowers/plans/audit_krkn_hub_tab.py`

The unit tests use fixtures. This runs the real 31 scenarios and both global pages against the real published pages.

- [ ] **Step 1: Port the script, with four changes**

The working script walks `HUB.glob("*/env.sh")`, pulls each published tab out of git, shells out to `python -m bot.doc_bot` into a temp dir, and diffs. Four adaptations:

1. Replace its bespoke markdown parsing with `published_table` / `published_cell` from Task 6, so the test and the bot cannot disagree about what a filled cell is.
2. Cover both sources: parameterise on `("krkn-hub", "krknctl")`.
3. **Seed the tab file into the temp website root before regenerating.** The script sets `WEBSITE_ROOT` to an empty temp dir, so `_published()` finds no tab, the rung never fires, and the test reports all 4 descriptions and all 34 types as lost against a *correct* implementation. This is the single most important adaptation.
4. Resolve the on-disk tab with `_find_tab(WEBSITE, scenario, source)` and take `rel = tab.relative_to(WEBSITE)`, rather than building `content/en/docs/scenarios/<scenario>/`. Only 12 of 31 match by name.

Guard it, since it needs three checkouts CI will not have:

```python
REQUIRED = (HUB / "node-scenarios" / "env.sh",
            KRKN / "containers" / "krknctl-input.json",
            WEBSITE / ".git")

pytestmark = pytest.mark.skipif(
    not all(p.exists() for p in REQUIRED),
    reason="needs local krkn-hub, krkn and website checkouts")
```

```python
@pytest.mark.parametrize("source", ["krkn-hub", "krknctl"])
def test_no_published_description_or_type_goes_blank(source, tmp_path):
    """A cell that has text today still has text after regeneration. There is no
    gate, so this is the only thing between a source gap and a published blank."""
    lost = []
    for scenario in sorted(p.parent.name for p in HUB.glob("*/env.sh")):
        rows = published_rows(scenario, source)     # via _find_tab + published_page
        if not rows:
            continue
        generated = generate(scenario, source, tmp_path, seed=rows)
        for name in rows:
            rec = generated.get(name)
            if rec is None:      # deleted from the source: dropping it is the job
                continue
            for col in ("description", "type"):
                if published_cell(rows, name, col) and not rec.get(col):
                    lost.append(f"{scenario}/{name}: {col}")
    assert lost == []
```

`published_page(rel)` is the script's `git show <ref>:<rel>` helper. Point it at a ref that still holds hand-written tables; `upstream/main` is the safe choice, since local `main` may already carry converted pages.

- [ ] **Step 2: The same assertion on the two global pages**

```python
def test_no_published_global_description_goes_blank(tmp_path):
    """SIGNAL_STATE and RESILIENCY_RUN_MODE both carry a long published
    description and no source has one, so they are what this catches."""
    for _source, rel in g._PAGES:
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(published_page(rel), encoding="utf-8")
    g.emit(tmp_path, HUB, KRKN)
    lost = []
    for source, rel in g._PAGES:
        rows = published_table(published_page(rel))
        # Guard against a wrong ref making this vacuously green.
        assert len(rows) > 40, f"{rel}: fixture did not load"
        generated = {r["name"]: r for r in yaml.safe_load(
            (tmp_path / "data/params/globals" / f"{source}.yaml")
            .read_text(encoding="utf-8"))["params"]}
        for name in rows:
            if (name in generated and published_cell(rows, name, "description")
                    and not generated[name].get("description")):
                lost.append(f"globals/{source}/{name}")
    assert lost == []
```

The `len(rows) > 40` assertion matters: `git show` failures are swallowed by the helper, `published_table("")` returns `{}`, and the loop would then pass having checked nothing.

- [ ] **Step 3: Sanity-check the numbers directly**

```bash
cd /c/Users/nayus/Desktop/LFX/krkn_Sync/krkn-docs-bot-gh-aw/krkn-docs-bot-gh-aw
PYTHONPATH=$PWD python -c "
from bot.globals import build_groups
ctl, env = build_groups(r'C:\Users\nayus\Desktop\LFX\krkn_Sync\krkn-hub', r'C:\Users\nayus\Desktop\LFX\krkn_Sync\krkn')
print('krknctl', len(ctl), 'no desc', sum(1 for r in ctl if not r.description))
print('krkn-hub', len(env), 'no desc', sum(1 for r in env if not r.description))
"
```

Expected: `krknctl 78 no desc 0` and `krkn-hub 75 no desc 6`.

- [ ] **Step 4: Commit**

```bash
git add tests/test_no_regression_audit.py
git commit -s -m "Assert the full corpus never loses a published cell"
```

---

### Task 14: End-to-end fork run

- [ ] **Step 1: Push**

```bash
git push origin main
```

`doc-sync.md` pip-installs from this repo's `main`, so the bot needs no redeploy. The workflow change in Task 12 does need the recompiled lock pushed to `website_2`.

- [ ] **Step 2: Trigger a scenario sync**

Comment `/fix node-scenarios demo-scenario` on any website_2 PR, or push a change to a scenario's `env.sh` on the krkn-hub fork.

- [ ] **Step 3: Trigger the globals path**

Still never exercised end to end. Merge a PR on the krkn fork touching `containers/krknctl-input.json` and confirm the trigger dispatches the literal `globals`, or run `/fix globals` directly.

- [ ] **Step 4: Check the resulting PR**

- Commit message carries the report, with `VERIFY_SESSION` listed as `published-table`
- Hugo Build Check passes
- The krknctl tab shows `--action`, and `bmc-password` reads `string (secret)`
- `SIGNAL_STATE` and `RESILIENCY_RUN_MODE` keep their descriptions
- Both global pages still render every group, not just the first
- `data/params/globals/krknctl.yaml` gained no `flag:` keys, since every global row has `name == flag`
- No `description_source: llm` rows at all on this run, because the residual is zero

- [ ] **Step 5: Force the model rung to fire**

Add a parameter to `demo-scenario/env.sh` with no comment, no `krknctl-input.json` entry and no published row. Confirm the model writes something, it is stamped `description_source: llm`, and the commit message lists it. Then add one whose obvious description would state a default the source does not have, to confirm the validator rejects it and the "Still blank" section renders with a reason.

- [ ] **Step 6: Revert the fixtures**

`demo-scenario`, `demo-zone-scenario`, and the removal of `DISKS` from `node-scenarios` are all test fixtures on the krkn-hub fork. Revert all three before any upstream work.

---

## Out of scope

- A gate that refuses injection. Rejected in the spec's Principle section.
- Letting the agent edit files. Rejected; gh-aw's `post-steps` compile after patch collection, so the containment step has nowhere to run.
- Routing the gap report to the krkn-hub drift issue. `github_client` is a dumb setter and the body is composed by `drift_scanner.format_report`, so this is a `drift_scanner` change.
- Unifying `globals.emit()` and `doc_bot._emit_one`.
- Type on the global krkn-hub page. The published page has no Type column.
- Hugo rendering tests. The harness exists only in docsync-bot; written during that port.
- `krknctl-input.json` description quality, which is krkn-hub#363.
- The scaffolded new-page placeholders, which need a maintainer decision first.
