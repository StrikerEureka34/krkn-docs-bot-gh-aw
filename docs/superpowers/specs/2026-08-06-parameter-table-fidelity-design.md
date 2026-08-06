# Parameter table fidelity

**Goal:** make the generated parameter tables match or beat the hand-written ones
they replace, on every krkn-hub scenario and on the two global pages, without the
bot ever destroying information it cannot regenerate.

**Status:** approved, not yet implemented.

&ensp;

## Why

The first real end-to-end run ([website_2#61](https://github.com/StrikerEureka34/website_2/pull/61),
driven by [krkn-hub#49](https://github.com/StrikerEureka34/krkn-hub/pull/49))
regenerated `node-scenarios` and the result was worse than the page it replaced.
Hugo built it, every check went green, and the output was still a downgrade.

That is the important part. Nothing failed. The bot did exactly what it was told
and quietly deleted curated work, because the sources it reads are less complete
than the pages they are meant to generate.

An audit across all 31 scenario pages, comparing the published krkn-hub tab
against what the bot would emit today:

| Outcome | Rows |
| --- | --- |
| Published description survives unchanged | 21 |
| Goes blank: no krknctl entry and no `env.sh` comment | 4 |
| Replaced by a weaker krknctl description | 9 |
| Published rows carrying a `Type` cell the bot cannot produce | 34 |

The four that go blank are `node-scenarios/VERIFY_SESSION`,
`node-scenarios/SKIP_OPENSHIFT_CHECKS`, `pvc-scenario/BLOCK_SIZE` and
`service-disruption-scenarios/SLEEP`.

One of the nine replacements is the bot being **right**: `CLOUD_TYPE`'s published
list omits azure and gcp. That one must not be "fixed".

The krknctl tab has its own problems, independent of descriptions:

| Aspect | Published | Generated | Verdict |
| --- | --- | --- | --- |
| Parameter | `--action` | `ACTION` | Wrong. The tab documents `krknctl run`. |
| Secret params | `string (secret)` | `string` | Lost. 26 entries carry `secret: "true"`. |
| Column order | Type, Required, Default, Possible Values | Type, Possible Values, Default, Required | Widest column wedged in the middle. |
| Empty Possible Values | blank | `-` | Two thirds of rows are non-enum. |

**One row shape the audit does not cover.** A parameter present in the published
table but in neither source produces no row at all, because
`resolve_descriptions` iterates source records. The audit skips these by
construction, so the counts above exclude them. Deleting such a row is usually
correct, since removal from the source is the signal, but it is a whole row lost
rather than a cell, so it is worth reporting. See section 6.

&ensp;

## Principle

**The bot is additive. It never replaces a filled cell with an empty one, and it
never blocks a page from converting.**

Both halves matter. An earlier draft enforced the first half with a gate that
refused to inject a table when any cell would empty. That was rejected: it froze
an entire page over one blank cell, it would have refused on cases where the bot
was correct (`NODE_NAME` publishes a default of `""` while `env.sh` declares
none), and it left the page and its data file disagreeing with nothing watching.
The replacement is a fallback chain, so a missing cell degrades one cell instead
of stopping a page.

&ensp;

## 1. The description chain

```
env.sh comment -> krknctl description -> existing YAML -> published table -> model -> blank
```

Each rung only runs when every rung above it produced nothing.

- **`env.sh` comment** and **krknctl description** are the sources. Already
  implemented and already correctly ordered. `resolve_descriptions` prefers the
  source over everything, which is why `CLOUD_TYPE` improves rather than
  regressing.
- **Existing YAML** already exists at `descriptions.py:18`. Its docstring reads
  *"Existing stays as a fallback for params neither source describes."*
- **Published table** is new. It reads the hand-written markdown table off the
  tab file before the shortcode replaces it. This is what stops the 4 blanks and
  the 34 lost Type cells.
- **Model** is new. See section 4.
- **Blank** is always a legal outcome and is reported. See section 6.

`type` uses the same chain minus the model, since a type is not prose and
guessing one is a different kind of claim.

**The model rung has no work to do today.** All four blank descriptions have
curated text in their published tables, so rung four fills every one of them and
the residual across the whole corpus is zero. It is built anyway, because the
first genuinely new parameter with no published row is the case it exists for,
and because building it now is cheap. Nobody should expect it to fire on the
first run.

&ensp;

### Two joins that are easy to get wrong

**Page directories do not match scenario names.** `hog-scenarios/cpu-hog-scenario`
is the page for `node-cpu-hog`; `network-chaos-ng-scenarios/node-interface-down`,
`node-scenarios/node-scenarios-bm`, `kubevirt-vm-outage-scenario`,
`power-outage-scenarios` and `zone-outage-scenarios` diverge the same way. Only
12 of the 31 scenarios match a page directory by name. `scaffold._find_tab`
already resolves this through the `<krkn-hub-scenario id="...">` marker and is
regression-tested. The published-table reader must use it rather than building a
path from the scenario name, or carry-forward is dead for more than half the
corpus.

**The krknctl page keys rows by CLI flag, the data file keys them by env var.**
`published_table` strips the leading `--`, so its keys are `action` while records
carry `ACTION`. The lookup has to bridge with `r.flag or r.name`, the same
expression the emitter uses. This is currently masked: all 278 per-scenario
krknctl params already have a description and a type, so a test on that source
passes whether or not the bridge exists.

&ensp;

### Every rung must survive regeneration

A rung is only worth having if its result is still there on the next run, and two
of them are not:

- The published table is **destroyed by the same run that reads it**.
  `scaffold_scenario` replaces it with the shortcode call, so run 2 sees no table.
  Anything rung four supplies must be picked up by rung three afterwards or it
  lasts exactly one commit.
- `load_descriptions` returns `{name: description}` and nothing else, so rung
  three carries descriptions only. A `type` carried from the published table
  renders on run 1 and renders `-` on run 2. `_param_dict` never writes
  `description_source` at all, so the provenance guarantee in section 3 expires
  the same way.

Both are fixed by widening the read-back, not by adding rungs: the existing-file
rung returns `description`, `type` and `description_source`, and `_param_dict`
emits `description_source`. Without that, sections 3 and 8 are untrue after the
first regeneration.

&ensp;

### `default` is excluded, permanently

`default` is never carried forward and never generated. `env.sh` is authoritative
for defaults, and a published default that disagrees with the source is exactly
the config drift this bot exists to detect. Carrying it forward would suppress
the bot's primary function.

&ensp;

## 2. The globals path

`globals.emit()` has its own copy of the load-existing, resolve, emit sequence and
calls `resolve_descriptions` without `published`, so none of section 1 reaches it
for free. Measured through `build_groups` against the real sources:

| | krknctl globals | krkn-hub globals |
| --- | --- | --- |
| Records | 78 | 75 |
| Missing a description | 0 | 6 |
| Missing a type | 0 | 75 |

The krknctl side is complete. The krkn-hub side is not: `RETRY_WAIT`,
`PUBLISH_KRAKEN_STATUS`, `SIGNAL_ADDRESS`, `PORT`, `SIGNAL_STATE` and
`RESILIENCY_RUN_MODE` have no description from any source, and at least three
have curated text on the published page today, including a long one on
`RESILIENCY_RUN_MODE`. Without the published-table rung, the first upstream run
blanks them exactly the way `node-scenarios` was blanked.

So `globals.emit()` gets the published-table rung and nothing else.

Type is deliberately left alone here. All 75 krkn-hub global records lack one,
but the published page is `Parameter | Description | Default` with no Type column
at all, so filling it would be a new feature rather than a repair.

One structural difference matters for the parser: the global pages carry **one
table per group**, not one table per page. `scaffold._tables()` already returns
every table on a page, because `inject_global_shortcodes` needed exactly that, so
the published-table reader is built on it rather than on a first-table-only scan.

&ensp;

## 3. Provenance

`ParamRecord` already carries `description_source` (`"env-comment"`,
`"krknctl"`). Extend the vocabulary to include `"published-table"` and `"llm"`,
and write it into the data file:

```yaml
- name: DRAIN_TIMEOUT
  description: Seconds to wait for a node to drain
  description_source: llm
```

Two changes make this real, and neither exists today: `_param_dict` has to emit
the field, and the existing-file read-back has to return it. Without both, the
marker survives one commit and the audit story below is false.

The audit story is the point. Every description the bot did not take from a
source file is findable with one grep and removable in one pass. It is also
self-healing: source stays at rung one, so the moment someone adds the `env.sh`
comment the real text wins and the marker disappears on the next run.

&ensp;

## 4. The model rung

Python calls the model. The gh-aw agent is not involved and its prompt does not
change.

&ensp;

### Why Python and not the agent

The alternative was letting the agent edit the data files, with a deterministic
step between the agent and the pull request discarding anything outside its work
order. **That containment step has nowhere to run.** Verified by compiling a probe
workflow: the custom pre-agent step lands at line 427, the agent at 744,
`Ingest agent output` (`id: collect_output`) at 873, and `post-steps` at 950. The
pull request is built from `/tmp/gh-aw/aw-*.patch`, which `create_pull_request`
consumes under `max_patch_files` and `max_patch_size` limits, and that patch is
fixed at collection time. A post-step can commit whatever it likes and none of it
reaches the pull request. There is no user-controlled hook between the agent and
collection.

Calling the model from Python removes the problem rather than relocating it.
There is no untrusted process touching files, so there is nothing to contain.
Validation, provenance and caching all happen in the language that already holds
the data.

It is also the lighter ask of whatever endpoint serves it. This rung wants one
completion with no tools and no loop. The agent route wanted a multi-turn session
with MCP tool calls, file editing and a correctly-formed safe-output invocation,
which is a much harder thing for a small local model to get right.

&ensp;

### Where it runs

In the existing custom `steps:` block, alongside generation. Two facts make this
nearly free:

- **Custom steps run outside the firewall.** They land at lock lines 523-620;
  AWF is installed at 625 and only wraps the agent execution at 938. So the call
  needs no `network.allowed` entry. That list governs the agent's sandbox, not
  this step.
- **`COPILOT_GITHUB_TOKEN` already exists** as a declared secret, validated at
  lock line 237. Line 988 shows gh-aw deliberately excludes it from the agent
  sandbox (`--exclude-env COPILOT_GITHUB_TOKEN`), so it is a runner-level secret,
  which is exactly where this step runs.

So the first implementation targets GitHub Copilot's OpenAI-compatible endpoint
with the secret that is already there: no new secret, no new allowlist entry, no
workflow permission change. **This needs verifying before it is relied on**, since
that token is issued for Copilot CLI and the endpoint may refuse it for raw chat
completions. A dedicated key is the fallback and changes nothing else.

Moving to the Mac mini later is two environment variables:

```yaml
env:
  OPENAI_BASE_URL: https://<hostname>/v1
  OPENAI_API_KEY: ${{ secrets.<key-name> }}
```

Because the target is a plain OpenAI-compatible endpoint, the whole rung runs on
a laptop against the same box, so prompts can be tuned without a workflow run and
without spending AIC. That is worth as much as the containment argument.

&ensp;

### Context is assembled deterministically

The objection to Python calling the model was that it only gets what the code
serialises. That is a feature: the code has the same checkouts the agent would,
and it can choose better than a three-turn model browsing on its own.

```python
def _context(scn, record, siblings):
    """Everything the model needs, assembled the same way every time."""
    return {
        "scenario":  scn.name,
        "readme":    _head(scn / "README.md", 2000),
        "line":      record.raw_line,          # the export with its default
        "krknctl":   {"type": record.type, "values": record.allowed_values,
                      "required": record.required},
        "examples":  [(s.name, s.description) for s in siblings
                      if s.description][:5],
    }
```

`examples` is the part the agent route could not do reliably. Feeding five real
descriptions from the same scenario keeps the generated sentence in the house
voice instead of drifting to model-default phrasing. Curation belongs in code.

One batched call per scenario, `temperature: 0`, structured JSON back.

&ensp;

### Fail soft

```python
def describe(scenario, names, ctx):
    """{name: sentence}. Returns {} on any failure: timeout, bad JSON, non-200,
    endpoint unreachable."""
```

Any failure leaves the cells blank, which is already a legal outcome and is
already reported, so the run still produces a correct pull request. This is what
makes it safe to point at a single self-hosted box later: the rung degrades to
exactly today's behaviour. The agent turn has no such property, since opening the
PR is its only job.

&ensp;

### Validation

Each returned string must be a single line, at most 120 characters, must not
contain a number or quoted literal absent from the source record (this is what
stops it inventing a default), and must not match the placeholder shape
`descriptions.py:25-26` already warns about. A rejection is not an error: the
cell stays blank and the report carries the reason and the rejected text, which
is the only feedback loop for tuning the validator.

Generation runs once per parameter, ever. The value is cached in the data file
and reused from rung three afterwards, so the pipeline is deterministic given its
committed state and produces no diff churn.

&ensp;

## 5. Text safety

Generated text flows into three structured formats. Two are already safe.

- **YAML** is safe. `emitter.py:33` uses `yaml.dump`.
- **Shell** is safe as long as the text never reaches a `${{ }}` expression.
  Actions substitutes those into the script source before bash parses it, so that
  is the real injection point, not the heredoc: a heredoc delimiter is matched
  during parsing, before variable expansion, and expansion results are not
  re-scanned. Text travels by file or env var.
- **Markdown tables** are not safe. A description containing `|` silently adds a
  column and a newline breaks the row. One helper collapses whitespace and
  escapes pipes at the point the cell is built. Note that an escaped `\|` still
  contains a pipe character, so any test counting pipes has to discount them.

&ensp;

## 6. Reporting

**The website PR reviewer** needs to know which cells are not source-derived
before approving. This goes in the commit message, which `doc-sync.md:99-101`
already establishes as the deterministic channel that never passes through the
agent. Python writes the sections to a file and the shell appends it:

```markdown
### Descriptions not taken from source (3)

| Scenario | Parameter | Filled from | Text |
| --- | --- | --- | --- |
| node-scenarios | SKIP_OPENSHIFT_CHECKS | published table | Skip OpenShift-specific cluster checks (set to true for vanilla Kubernetes) |
| node-scenarios | VERIFY_SESSION | published table | Verify the SSH session during node scenarios |
| pvc-scenario | BLOCK_SIZE | published table | Block size in bytes for the dd command used to fill the PVC |

### Still blank (1)

| Scenario | Parameter | Why |
| --- | --- | --- |
| demo-scenario | NEW_PARAM | rejected: contains a value not in the source ("1024") |

These render as an empty cell. Fix by adding a trailing comment in env.sh:
  export NEW_PARAM=${NEW_PARAM:=1024}   # Size of each written block
```

Those are the real rows the first run produces, all `published table`. A third
section reports rows present in the published table and in no source, so an
unintended deletion is visible rather than silent.

All three sections are omitted when empty, so a clean run has a clean commit
message.

The report is written once per run, not once per scenario. The workflow loops
over targets and invokes the bot per target, so the writer has to append or the
last target erases the rest.

**The krkn-hub maintainer** is the only person who can fix any of this, and they
never see the website PR. Routing the list to the drift issue is the obvious
answer and is **out of scope here**, because `github_client.create_or_update_drift_issue`
is a dumb setter: the body is composed by `drift_scanner.format_report`, which
merges the previous body to preserve ticked checkboxes. Adding a section is a
`drift_scanner` change, and `find_open_drift_issue` returns the first match, so a
second labelled issue would break it. That work is real but belongs with the
drift reporter.

&ensp;

## 7. krknctl tables show CLI flags

`ParamRecord.flag` already carries the krknctl `name` field. Nothing reads it on
the per-scenario path.

- `emitter._param_dict` emits `flag` alongside `name` for the krknctl source
- `param-table.html` renders `flag` when present, `name` otherwise
- `scaffold.py` passes `prefix="--"` for the krknctl source at the two
  per-scenario call sites, matching what it already does for globals

`name` stays the env var permanently. This matters:

- `drift_scanner.py` keys the krknctl source on the env var and compares against
  the committed table by `name`. Change what `name` holds and every parameter
  reports as both missing and extra.
- `build_skip_list` returns env var names and `doc_bot.run()` filters on them.
  A swap performed before that filter matches nothing, so every global param
  leaks into every scenario table.

Emitting both identifiers avoids both couplings rather than working around them.

Globals needs one guard. `globals.build_groups` swaps the flag into `name` using
`dataclasses.replace`, which copies every field it is not told to change, so
`flag` survives and all 78 krknctl global records have `name == flag`. Emitting
both unconditionally would add a duplicate key to every row for no visible
change, since the shortcode falls back to `name` anyway. `flag` is therefore
emitted only when it differs from `name`.

&ensp;

## 8. Type on the krkn-hub tab

`env.sh` has no type information. `doc_bot.run()` already joins env params to
their krknctl counterparts to borrow descriptions; extend that join to carry
`type`.

That covers 30 of the 34 rows. The remaining 4 are exactly the params with no
krknctl counterpart, which are the same four that go blank: `VERIFY_SESSION`,
`SKIP_OPENSHIFT_CHECKS`, `BLOCK_SIZE` and `SLEEP`. They fall through to the
published table at rung four, and stay only if the read-back in section 1 is in
place.

The helper is renamed, since it stops being description-only. Its current filter
(`if r.description`) has to go: a krknctl entry with a type and no description
must still contribute its type.

&ensp;

## 9. Secret marker

`ParamRecord` gains `secret`. The parser reads the field, the emitter emits it for
the krknctl source, the shortcode renders the type cell as `string (secret)`.

26 entries, 13 distinct parameter names, across 4 scenarios: `node-scenarios`
(11), `power-outages` (11), `zone-outages` (3) and `dummy-scenario` (1). Plus one
global, `TRIGGER_HTTP_BEARER_TOKEN`, which the globals page picks up for free
since it emits through the same krknctl source.

The field is the **string** `"true"`, not a boolean, so it needs `_as_bool` and
not a truthiness check.

Not covered by the fallback chain, because `string (secret)` degrading to
`string` is a filled cell staying filled. It has to be fixed additively or it is
lost silently.

&ensp;

## 10. Rendering changes

The only part of this spec that changes existing output rather than adding to it.

- **Possible Values moves last.** It is the widest column and currently pushes
  Default and Required off-screen.
- **Empty Possible Values renders blank, not `-`.**
- **Default keeps its `-`.** There the dash distinguishes "no default declared"
  from `default: ""`, a distinction that only just started rendering correctly.
  Do not collapse them again.
- **Required renders Yes/No** rather than true/false.

&ensp;

## 11. Files touched

| File | Change |
| --- | --- |
| `bot/parser.py` | read `secret` via `_as_bool`; add the field to `ParamRecord` |
| `bot/emitter.py` | emit `flag` (only when it differs from `name`), `secret` and `description_source`; widen the existing-file read-back to return type and provenance |
| `bot/descriptions.py` | published-table rung; stamp provenance; return the gap list |
| `bot/doc_bot.py` | krknctl join carries `type`; drop the description-only filter; resolve the tab through `_find_tab`; bridge flag to env var; assemble model context; collect gaps |
| `bot/globals.py` | pass the two global pages' tables into `resolve_descriptions` |
| `bot/scaffold.py` | published-table reader over every table on a page; `prefix="--"` at the two per-scenario call sites |
| `bot/describe.py` (new) | the model call, validation, fail-soft |
| `bot/report.py` (new) | build the commit-message sections; escape table cells |
| `website-template/layouts/shortcodes/param-table.html` | render `flag`; secret in the type cell; column order; blank vs dash |
| `.github/workflows/doc-sync.md` | pass the endpoint env to the generate step; append the gap report to the commit message from a file |

`bot/drift_scanner.py` stays untouched. If it needs editing, section 7 is wrong
and should be revisited before patching around it. The exception is the
maintainer-facing report in section 6, which is explicitly out of scope for that
reason.

`bot/globals.py` gets exactly one change. An earlier draft listed it as
untouched, which was wrong: it forked the emit path from `doc_bot`, so an
improvement to one does not reach the other and the divergence does not announce
itself. Unifying the two is worth doing and is not in this change.

The agent prompt does not change. Its only job stays opening the pull request,
`max-turns` stays at 3, and it gains no file-editing grant.

&ensp;

## 12. Testing

Unit test per change. Beyond that:

- The audit script becomes a regression test across all 31 scenarios: no
  published description or type goes blank. It must seed the tab files into the
  temp website root before regenerating, or the published rung never fires and
  the test fails against a correct implementation.
- The same assertion on the two global pages, with a positive assertion that the
  fixture actually loaded (`SIGNAL_STATE` present), since an empty fetch would
  otherwise make it pass vacuously.
- A two-run test: emit, remove the tab, emit again, assert the carried type and
  the provenance marker both survive. This is the one that catches the read-back
  gap in section 1.
- `bot/describe.py` is tested against a fake transport, never a live endpoint.
  The cases that matter are the failure ones: non-200, malformed JSON, a missing
  key, a timeout. Every one returns `{}` and leaves the cells blank.
- There is **no** Hugo rendering test in this repository. `tests/test_param_table.py`
  and the `Site` fixture exist only in docsync-bot, so the four rendering changes
  in section 10 have no automated coverage here and are verified by rendering the
  real site. Writing them belongs to the docsync-bot port.

&ensp;

## 13. Upstream

A sibling issue to [krkn-hub#363](https://github.com/krkn-chaos/krkn-hub/issues/363),
same table shape.

#363 compared the 246 krknctl flags against the published **krknctl** table. The
krkn-hub tab is a separately curated set that was never in that comparison.
Overlap is exactly one row, `node-scenarios/--disable-ssl-verification`, which
#363 already proposes fixing.

Scope: 4 parameters needing a new `env.sh` inline comment, 8 needing a better
description, plus the 6 globals in section 2. `CLOUD_TYPE` is excluded, since the
source is already correct there.

There is a split worth stating explicitly in that issue, because it decides where
each description belongs:

- `env.sh` inline comments feed only the krkn-hub tab. They never reach a
  terminal, so they may contain markdown and links. This is the only home for
  `ACTION`'s `[following](/docs/scenarios/node-scenarios/)` link.
- `krknctl-input.json` descriptions feed the krknctl tab and the krkn-hub tab as
  fallback. #363 notes these reach `fmt.Printf`, so they must stay plain text.

The parser already prefers an `env.sh` comment over the krknctl description, so
this precedence needs no code. It is unused, not missing.

Carry-forward reduces the urgency of this issue but does not remove it. A carried
or generated description lives in a generated file rather than in the source, and
the commit message says so on every run until someone fixes it.

&ensp;

## Out of scope

- A gate that refuses injection. Considered and rejected; see Principle.
- Letting the agent edit files. Considered and rejected; see section 4.
- Routing the gap report to the krkn-hub drift issue. Requires a `drift_scanner`
  change; see section 6.
- Unifying `globals.emit()` and `doc_bot._emit_one`, which are two copies of the
  same sequence. This is why globals silently missed every improvement here until
  it was checked.
- Type on the global krkn-hub page. The published page has no Type column, so
  this is an addition rather than a repair.
- Description quality in `krknctl-input.json` for the krknctl tab. That is #363.
- `demo-scenario` and `demo-zone-scenario` on the krkn-hub fork are test
  fixtures, as is the removal of `DISKS` from `node-scenarios`. Revert all three
  before any upstream work.

&ensp;

## Open question for maintainers

The scaffolded page for a brand new scenario ships placeholders: empty
`description:`, `weight: 50`, and `TODO: scenario overview.`. `scaffold.py`
already carries a TODO saying the frontmatter format needs confirming. Worth
settling before the first new scenario lands upstream, since a reviewer has to
fill them by hand every time. The model rung deliberately does **not** extend to
this: page prose is a much larger claim than a parameter description and has no
source to check against.
