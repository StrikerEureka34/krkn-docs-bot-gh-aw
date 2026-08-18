# Bot Reference

What each module does, how the pieces fit, and how the tests are organised.

Companion to [fork-setup.md](fork-setup.md), which covers setup and operations.

We keep almost no counts in this file. The last version carried figures that were
all wrong within two weeks, so where a number matters we give the command that
produces it instead.

&ensp;

## 1. What we built

Against the project's original feature list:

| Feature | How it works today |
| --- | --- |
| Cross-repo trigger pipeline | Three triggers, on krkn-hub, krkn and krkn-operator, each firing on a push to the watched paths and dispatching the website with a short-lived GitHub App token |
| Deterministic extraction | A regex parser for `env.sh`, a JSON parser for `krknctl-input.json`, and a YAML parser for CRDs. Names, defaults, types and enums never involve a model |
| Model descriptions | One sentence per parameter, and **only** the Description column. Output is validated and rejected if it invents a value |
| Hugo data files and a shortcode | The bot writes `data/params/<group>/<table>.yaml` and never edits human markdown. `param-table.html` renders every table |
| Draft PR generation | Draft only, never auto-merged, prefixed `[docs-sync]`, with the full change detail in the commit message |
| Page scaffolding | Creates a page when none exists, for both scenarios and CRD kinds |
| Drift detection | A weekly scan of all three sources against committed data, kept in one rolling issue collapsed per source. Report only, no model |
| ChatOps | `/fix <target>` and `/resync`, gated by role. Both resolve to the same three target shapes through `targets.py` |
| Concurrency | One in-flight run per issue or PR, generated into the compiled workflow |
| Failure handling | The commit is staged and committed as one unit. A failed model call leaves cells blank, reports each one and keeps the run green. Hugo Build Check runs on the PR |
| Security controls | App tokens rather than PATs, SHA-pinned third-party actions, `permissions: read-all`, secret redaction in logs, and secrets stripped from the agent container |

Coverage reached three source repos: krkn-hub, krkn and krkn-operator, which
between them also give the krknctl surface.

&ensp;

## 2. The flow

```
source push -> trigger dispatches -> Doc Sync on the website
  parser / crd_parser  read the sources          -> ParamRecord
  descriptions         decide where each description comes from
  describe             fill what is left, via the model
  emitter              write data/params/<group>/<table>.yaml
  scaffold / operator  put a shortcode call on the page
  report               render the gap tables into the commit message
  -> deterministic step branches and commits, writing the gap tables into
     the commit message; the agent then opens the draft PR
  -> Hugo renders the YAML through param-table.html
```

`/resync` runs the same thing, with `targets.py` deriving the target list from the
paths the PR already changed.

Separately, weekly, `drift_scanner` re-reads the same sources, compares them
against the committed YAML and updates one rolling issue. It writes no files and
needs no model.

&ensp;

## 3. File map

| Module | Job |
| --- | --- |
| `parser.py` | Reads `env.sh` and `krknctl-input.json` into `ParamRecord`. Builds the skip list |
| `crd_parser.py` | Reads a CRD into `ParamRecord`: spec, status, and kubectl printcolumns |
| `descriptions.py` | Decides where each description comes from. The precedence chain lives here |
| `describe.py` | Calls the model for what nothing else supplied. Validates and rejects bad output |
| `emitter.py` | Writes the YAML data file, reads back the previous one |
| `scaffold.py` | Swaps a hand-written table for a `param-table` call. Creates a page if none exists |
| `doc_bot.py` | Entry point, one krkn-hub scenario, two tabs |
| `globals.py` | Entry point, the two global pages. Adds grouping |
| `operator.py` | Entry point, the krkn-operator api-reference pages. Adds the CRD index |
| `report.py` | Turns the gap list into the commit-message tables |
| `drift_scanner.py` | Report only. Compares sources against committed data |
| `targets.py` | Maps the website paths a PR changed to the targets that regenerate them |
| `github_client.py` | Finds or updates the rolling drift issue |

Plus two Hugo shortcodes in `website-template/layouts/shortcodes/`:
`param-table.html` renders a data file, `crd-ref.html` links prose to a generated
CRD page.

### Entry points

| Command | When | Writes |
| --- | --- | --- |
| `python -m bot.doc_bot --scenario X --scaffold` | Per krkn-hub scenario | `data/params/X/*.yaml`, the tab files |
| `python -m bot.globals --krkn-hub .. --krkn .. --scaffold` | The two global pages | `data/params/globals/*.yaml`, both pages |
| `python -m bot.operator --operator .. --website . --scaffold` | All 9 CRDs | `data/params/<plural>/*.yaml`, the index, the pages |
| `python -m bot.report` | Once, after the loop | `gaps.md` beside `gaps.jsonl` |
| `python -m bot.drift_scanner --krkn-hub .. --website .. --repo owner/name` | Weekly | Nothing. Opens or edits an issue |
| `python -m bot.targets --website .` | On `/resync` | Nothing. Reads changed paths on stdin, prints a space-separated target list |

**The three generators do not take their paths the same way.** This trips people
up, including us:

| Entry point | Website root from | Sources from |
| --- | --- | --- |
| `doc_bot` | `WEBSITE_ROOT` env, default `.` | `KRKN_HUB_PATH`, `KRKN_PATH` env |
| `globals` | `--website` flag, default `.` | `--krkn-hub`, `--krkn` flags, both required |
| `operator` | `--website` flag, default `.` | `--operator` flag, required |
| `targets` | `--website` flag, default `.` | stdin |

Passing `WEBSITE_ROOT` to `globals` or `operator` silently writes into the current
directory instead.

| Env var | Used by | Default |
| --- | --- | --- |
| `WEBSITE_ROOT` | `doc_bot` | `.` |
| `KRKN_HUB_PATH` | `doc_bot` | `krkn-hub` |
| `KRKN_PATH` | `doc_bot` | `krkn` |
| `GH_AW_REPORT_DIR` | `report` | unset means no report is written |
| `LLM_BASE_URL` | `describe` | the project endpoint |
| `LLM_API_KEY` | `describe` | unset means the model rung is skipped |
| `LLM_MODEL` | `describe` | the project model |

Locally: `pip install -e .`, clone the sources beside the website checkout, then
run a generator.

&ensp;

## 4. The model is swappable, and optional

`describe.py` speaks plain OpenAI-compatible `POST /chat/completions` over stdlib
`urllib`. There is no vendor SDK and no provider branch anywhere in the bot, so
any endpoint offering that shape works by setting three variables in the
generation step of `doc-sync.md`.

| Variable | What it selects |
| --- | --- |
| `LLM_BASE_URL` | The endpoint, ending in `/v1` |
| `LLM_API_KEY` | The bearer key, the only model credential |
| `LLM_MODEL` | The model that endpoint serves |

All three have built-in defaults, so a deployment that sets none of them still
runs. Swapping providers is a three-line change, not a migration: we have driven
it against GitHub Copilot and against NVIDIA NIM without touching the bot.

**The model is never load-bearing.** It writes one column. If the call fails,
times out or has no key, `describe()` returns `{}`, those cells stay blank, the
gap report names each one and the run stays green.

### Running fully deterministic

Descriptions are the only thing a model ever produces, so the pipeline can run
with no inference at all. Unset `LLM_API_KEY` and every rung except the model
rung still fires: source comments, the published table, the previous file, and the
other source. Only parameters that **no** source describes and no page ever
described come out blank, and each one is listed in the gap table.

| Rung | Needs a model |
| --- | --- |
| 1, source file | No |
| 2, published table | No |
| 3, existing data file | No |
| 4, other source or borrowed CRD field | No |
| 5, model | Yes |
| 6, blank and reported | No |

The krkn-operator source already runs this way permanently: every CRD field
carries its Go doc comment, so `operator.py` passes a stub that never calls out.

What this costs and what it keeps is in
[fork-setup.md](fork-setup.md#running-with-no-inference), along with the exact
settings to change.

&ensp;

## 5. Why three generators

The sources have three shapes, so one entry point cannot serve them.

| | `doc_bot` | `globals` | `operator` |
| --- | --- | --- | --- |
| Reads | `<scenario>/env.sh` + `<scenario>/krknctl-input.json` | root `env.sh` + `krkn/containers/krknctl-input.json` | `config/crd/bases/*.yaml` |
| Skip list | Applied, drops globals | None. It **is** the set the skip list is built from | None |
| Grouping | None | Required, three-tier fallback | None |
| Page target | Found by the `<krkn-hub-scenario id>` marker | Two fixed paths | One page per kind, written once |
| Name shown | Env var, flag as a separate key | The CLI flag | The field path |
| Model calls | Possible | Possible | **Never** |

### The data path is overloaded

All three write `data/params/<group>/<table>.yaml`, but the two segments mean
different things per source:

| Source | `<group>` | `<table>` |
| --- | --- | --- |
| krkn-hub | the scenario, e.g. `node-scenarios` | the source repo, `krkn-hub` or `krknctl` |
| globals | `globals` | the source repo, as above |
| krkn-operator | the CRD plural, e.g. `krknscenarioruns` | the section, `spec`, `status` or `columns` |

So an operator data file carries `source_repo: spec`, which holds a section name
rather than a repo. The shortcode only resolves a path, so it needs no change per
source.

&ensp;

## 6. ParamRecord

The spine. Everything else moves these around.

| Field | Set by | Used by |
| --- | --- | --- |
| `name` | Export name, krknctl `variable`, or CRD field path | Join key everywhere |
| `default` | `${V:=x}` body, krknctl `default`, or CRD `default` | Default column, drift compare |
| `required` | `export V=${V}` with no body, or CRD `required` | Required column |
| `type` | krknctl `type`, CRD `type`, or borrowed | Type column |
| `description` | Trailing `#` comment, krknctl `description`, or CRD doc comment | Rung 1 |
| `description_source` | Set as the chain resolves | Provenance, and the next run's filter |
| `allowed_values` | krknctl `allowed_values`, or CRD `enum` | Possible Values column |
| `group` | krknctl `group`, globals only | Shortcode `group=` filter |
| `flag` | krknctl `name` | The krknctl tab shows this, not `name` |
| `secret` | krknctl `secret`, or a CRD secret-ref heuristic | Renders `(secret)` in the Type cell |
| `borrowed_description` | The other source | Rung 4, never emitted directly |

`description_source` takes six values, and **only four reach the file**:

| Value | Meaning | Emitted |
| --- | --- | --- |
| `env-comment` | An `env.sh` trailing comment | No |
| `crd` | A CRD doc comment | No |
| `krknctl` | A krknctl `description` | Yes |
| `published-table` | The hand-written table we replaced | Yes |
| `crd-field` | A column borrowing the field its jsonPath names | Yes |
| `llm` | `describe.py` wrote it | Yes |

The two that are not emitted are the two that came from the row's own source file,
so one grep over `data/params/` finds every description the bot did not take from
source.

&ensp;

## 7. The description chain

| # | Rung | Where it comes from |
| --- | --- | --- |
| 1 | Source | The `#` comment, krknctl's `description`, or the CRD doc comment |
| 2 | Published table | The hand-written table on the website page |
| 3 | Existing file | The YAML the last run wrote |
| 4 | Other source | The other tab's wording, or the field a column points at |
| 5 | Model | `describe.py` |
| 6 | Blank | Reported as a gap, never papered over |

Two rules that are easy to break:

- **Rung 2 fires exactly once.** The run that reads the published table is the run that replaces it with the shortcode. `main()` calls `run()` before `scaffold_scenario()` for that reason. Split them into two jobs and every curated description that exists only on the page is lost, with nothing to recover it from.
- **Rung 2 outranks rung 4.** The published prose is the one rung a human wrote. It is fuller and carries links, so a terse one-liner must not overwrite it.

### What the model is not allowed to do

`validate()` rejects a generated description that:

- is empty, or contains a newline
- is longer than 120 characters
- says nothing, matching a placeholder like "Configures the port"
- **contains a number or quoted literal not already in that parameter's own record**

That last rule is the important one. A confidently wrong default is worse than a
blank cell, so an invented value is dropped and reported as a gap.

&ensp;

## 8. What keeps a second run identical

| Mechanism | Without it |
| --- | --- |
| Previous-file read-back | Once the table is gone, every page-only description goes blank on run 2 |
| `description_source` carry-forward | Provenance vanishes on run 2 and the YAML churns every run |
| Borrows excluded from `existing` | A terse borrow freezes forever and a better page row can never overtake it |
| Previous groups seed the page groups | A converted section has no rows left to read, so every global collapses to `other` and every `group=` call fails the build |
| A page is created only when the lookup returns `None` | A maintainer's added prose disappears on the next sync |

That last one covers the generated CRD pages too. The tables come from the CRD,
but the page around them is editable and a hand edit survives regeneration.

&ensp;

## 9. What a `/fix` can and cannot repair

`drift_scanner` emits six kinds of finding. Five are regenerable and one is not,
and the report has to say which is which. Getting it wrong in either direction is
a bug: a command that does nothing wastes a maintainer's time, and a missing
command makes the bot look less capable than it is.

| Kind | Means | Command |
| --- | --- | --- |
| `missing-table` | No data file exists for that source yet | `/fix <target>` |
| `missing` | The source has a param the table does not | `/fix <target>` |
| `stale` | A default or type moved in the source | `/fix <target>` |
| `missing-link` | Nothing links a generated CRD page yet, and `link_pages` will | `/fix operator` |
| `extra` | The table has a row the source dropped | `/fix <target>`, but it **deletes documented content**, so it is marked `⚠️ Review first` |
| `unlinked` | `link_pages` provably will not link it | **None**, and the finding names which of three blockers it is, marked `🔴 Maintainer needed` |

### `link_blocker`, and the bug that produced it

Until 2026-08-18 there was no `missing-link`. `operator_findings` decided
`unlinked` from one test, `plural not in linked`, where `linked` is scraped from
pages that happen to carry a `crd-ref` today. It never asked the question that
decides the answer: **would `link_pages` fix this?**

Against `website_2` that misfired on all 9 CRDs. Every one was mapped in
`_PAGE_LINKS`, every target page existed, and the issue still told maintainers
nine times to go hand-edit Python.

So `link_blocker` lives next to `link_pages` in `operator.py` and both call the
same `_page_ready` predicate. It returns `None`, or a `(reason, fix)` pair:

| Blocker | Whose job |
| --- | --- |
| `None` | The bot's. Emitted as `missing-link` |
| The kind is in no `_PAGE_LINKS` row | A person's, and editorial |
| Its mapped page does not exist | A person's, write the page |
| That page already carries a `crd-ref` | A person's, `link_pages` never touches such a page again |

The reason rides on the checkbox and the fix on the detail bullet, so neither
repeats the other and both are specific to that item.

**One case is deliberately not detected.** `_linked_crds` counts a `crd-ref`
anywhere outside `api-reference`, so a call placed on a page that does not
describe that kind satisfies it. Requiring the mapped page would make the bot's
hardcoded guess outrank a maintainer's choice, and `link_pages` writes the mapped
page regardless, so the cost is a stray link rather than a broken one.

### Why `Finding` carries a `target`

The report groups by `scenario`, which for the operator source is the CRD plural,
because that is the heading a reader recognises. But no `/fix krknusers` exists:
`bot.operator` is the only thing that regenerates a CRD table, and it does all of
them. So `operator_findings` sets `target = "operator"` on every finding it
builds, and `format_report` renders `f.target or f.scenario`. Display grouping and
action grouping are different axes; collapsing them is what produced a command
that parsed fine and did nothing.

One target for all kinds is deliberate rather than lazy: regeneration is
idempotent and git stages only real changes, so a per-CRD target would emit an
identical diff through a second code path.

### The layout

`format_report` wraps each source in a `<details>` so the issue opens as three
lines instead of the ~350 the flat version reached. `_GROUP_ORDER` fixes the
order; `_group_of` picks a group from the findings themselves, `operator` by
`target` and `globals` by scenario name, so nothing is keyed off a hardcoded list
of scenarios.

A group header carries a `🔴 N need a maintainer` count when it has any, because
a marker inside a collapsed group is invisible, which would defeat the collapse.

Ticks are matched against the rendered checkbox label, which encodes the finding
counts. A finding that changes therefore loses its tick, so new drift cannot hide
behind a box someone already ticked. The parser accepts a body with no `<details>`
in it at all, which is what the first run after a layout change reads.

The markers are emoji rather than `$\color{red}$`. They have to render in a
collapsed `<summary>`, in notification email and on mobile, and none of those run
a math renderer. `main()` also reconfigures stdout to UTF-8 before printing,
since a Windows console defaults to cp1252 and a preview run should not die on
its own output.

&ensp;

## 10. Tests

```bash
pytest -q
```

To see the current count and distribution:

```bash
pytest -q | tail -1
grep -c "^def test" tests/*.py | sort -t: -k2 -rn
```

| Area | Files | Why it exists |
| --- | --- | --- |
| Source parsing | `test_parser.py`, `test_crd_parser.py` | Shell expansion and CRD schemas are full of traps. A mis-parse writes a wrong default into a published table |
| Description precedence | `test_description_resolution.py`, `test_describe.py` | The rung order itself, and stopping a hallucinated default reaching the docs |
| Emission and provenance | `test_emitter.py` | Losing the provenance marker is what makes a borrow freeze |
| Page scaffolding | `test_scaffold.py`, `test_scaffold_globals.py` | Stops the migration eating prose, targeting the wrong page, or re-injecting every run |
| Generators | `test_doc_bot.py`, `test_globals.py`, `test_operator.py` | End to end per entry point |
| Drift and reporting | `test_drift_scanner.py`, `test_report.py`, `test_github_client.py` | Stops the drift issue lying: new drift hiding behind a ticked box, a fresh issue every week, or a `/fix` that names a target no generator answers to |
| Target resolution | `test_targets.py` | The only cover `/resync` has. A fork PR gets no secrets, so this path cannot be exercised in CI |
| Shortcode rendering | `test_param_table.py` | Column auto-hide, numeric-zero defaults, markdown links, failing the build on missing data |
| Corpus audit | `test_no_regression_audit.py` | Runs the real corpus against the real pages, the only way to know the chain fires |

### What needs setup

| Group | Needs | Without it |
| --- | --- | --- |
| Shortcode rendering | Hugo extended and `beautifulsoup4` | Fails to find a hugo binary |
| Corpus audit | Local `krkn-hub`, `krkn` and `website` checkouts, and a resolvable `upstream/main` | **Skips cleanly.** A missing ref, however, is an error not a skip |
| Everything else | Nothing | Runs anywhere |

The corpus audit finds the sibling checkouts by directory depth, which only works
when the repo sits beside them. Otherwise point it explicitly:

```bash
WEBSITE_REPO=../website KRKN_HUB_PATH=../krkn-hub KRKN_PATH=../krkn pytest -q
```

`conftest.py` strips `LLM_API_KEY` before every test, so the suite can never call
a live endpoint.

&ensp;

## 11. Coverage

Four coverages, three source repos. See
[fork-setup.md](fork-setup.md#2-what-we-cover) for what each one feeds.

Stable facts worth stating: krkn-operator has **9 CRDs** producing **10 pages**,
and the krknctl surface is read from files living inside krkn-hub and krkn, never
from the krknctl repo.

Everything else moves, so measure it rather than trusting a number here:

```bash
# how many scenarios have each source file
ls -d krkn-hub/*/env.sh | wc -l
ls krkn-hub/*/krknctl-input.json | wc -l

# how much the operator source emits
python -m bot.operator --operator krkn-operator --website . | wc -l

# how many pages already use a shortcode rather than a hand-written table
grep -rl "param-table" website/content/ | wc -l
```

The asymmetry that justifies the whole fallback chain: krkn's
`krknctl-input.json` describes nearly every parameter it declares, while
krkn-hub's `env.sh` files describe almost none. Both cover largely the same
variables, which is why the two sources borrow from each other. Re-measure with:

```bash
grep -c "#" krkn-hub/*/env.sh | sort -t: -k2 -rn | head
```

&ensp;

## 12. Known gaps

**No open defect in the bot's own logic.** What is left is two things outside the
package and one deliberate boundary:

| # | Gap | Where |
| --- | --- | --- |
| 1 | The krkn-hub and krkn triggers still dispatch to a fork. The krkn-operator one does not | `krkn-hub-template/`, `krkn-template/` |
| 2 | The krkn source, link integrity and config-block drift, is still an open PR | `docsync-bot` PR #12 |
| 3 | A `crd-ref` on a page that does not describe that kind is counted as linked. A boundary, not a defect: see §9 | `drift_scanner.py`, `_linked_crds` |

Item 1 is covered in
[fork-setup.md](fork-setup.md#gaps-to-close-in-the-shipped-template).

### Closed

| Was | Now |
| --- | --- |
| An ambiguous page marker took the first match | `_find_scenario_dir` raises on a duplicate id, and sorts so the answer never depends on the runner's filesystem order |
| The skip list dropped a scenario override without comparing defaults | `build_skip_list` carries each default, and `is_global` keeps a param whose default the scenario changed |
| `/resync` routed CRD plurals to the krkn-hub generator | `targets.py`, unit-tested because a fork PR gets no secrets |
| The shipped template cloned no krkn-operator and had no `operator` route | Both in `website-template/doc-sync.md` |
| `emitter.py` keyed two conditions off the source **name**, so every CRD enum and secret marker would have been dropped | Narrowed, and pinned by three tests |

### Landing in `fix/describer-config`, not the operator PR

Choosing an inference endpoint is a separate decision from adding a source, so
these ship as the second PR:

| | |
| --- | --- |
| `_TIMEOUT` hardcoded at 30s | Reads `LLM_TIMEOUT`, default 120s. The same prompt measured 20.6s, 27.4s and 83.3s within one hour on a free tier |
| The template wired no describer | `LLM_*` set, NVIDIA NIM active with Copilot commented beside it |
| Nothing forced the bearer onto TLS | `describe.py` refuses a non-`https` `LLM_BASE_URL` rather than sending the key |
