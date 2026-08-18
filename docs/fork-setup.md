# Docs Sync Bot: Setup and Operations

How we run the docs sync bot on the `krkn-chaos` repos: what to install, what to
set in org settings, how to drive each source, and what has already gone wrong.

Secret **names** only in this file. No values.

For internals, the description chain and the test suite, see
[bot-reference.md](bot-reference.md).

&ensp;

## 1. What it does

A source repo changes, the website regenerates its parameter tables, a draft PR
opens. No human markdown is ever rewritten.

```
krkn-hub / krkn / krkn-operator push
  -> trigger-docs-sync.yml dispatches, with an App token
  -> Doc Sync runs on the website repo
     -> Python reads the sources and writes data/params/**.yaml
     -> the param-table shortcode renders those files as tables
     -> a deterministic step branches, commits and requests the PR
  -> a draft PR opens, never auto-merged
  -> Hugo Build Check renders it
```

### Two model calls, and they are independent

| | Where | Job | Switch | If it fails |
| --- | --- | --- | --- | --- |
| Call 1, the describer | `bot/describe.py`, a plain Python step | Writes descriptions no source file has | `LLM_API_KEY` | Cells stay blank, the gap report names each one, **the run stays green** |
| Call 2, the engine | The gh-aw agent, after every custom step | Opens or updates the PR | `engine:` | The run fails |

Two things follow:

- Call 1 runs **before** the network firewall is installed, so its host needs no `network.allowed` entry.
- Call 2 runs inside the firewall. See [section 6](#6-the-engine), which is where all our trouble was.

&ensp;

## 2. What we cover

Four coverages across three source repos. The website is the target, not a
source.

| # | Coverage | What we read | Where it lands |
| --- | --- | --- | --- |
| 1 | krkn-hub | `<scenario>/env.sh` | the krkn-hub tab on each scenario page |
| 2 | krknctl | `<scenario>/krknctl-input.json` and `krkn/containers/krknctl-input.json` | the krknctl tab, and the global pages |
| 3 | krkn | `containers/krknctl-input.json` for globals, plus link integrity and config-block drift on `_tab-krkn.md` | the two global pages, and prose tabs |
| 4 | krkn-operator | the 9 CRDs under `config/crd/bases` | `api-reference/`, 10 pages of tables |

**We get krknctl coverage for free.** We never read the krknctl repo. The files
that define its CLI surface ship inside the other two: 29 `krknctl-input.json`
files in krkn-hub, 1 in krkn. The krknctl repo holds exactly one, and it is a test
fixture under `tests/containerfiles/`.

So "krknctl" in the bot means two things, neither of which is the repo:

- a **source label**, picking which data file to write and which tab to inject
- the **CLI flag** (`--action`) from an entry, as opposed to its variable (`ACTION`)

&ensp;

## 3. Driving one source at a time

Everything runs through one workflow on the website, `doc-sync`, selected by a
**target**. A target is a scenario id, or one of two special names.

| Target | Runs | Covers |
| --- | --- | --- |
| `<scenario>`, e.g. `node-scenarios` | `bot.doc_bot --scenario <s>` | one krkn-hub scenario, both tabs |
| `globals` | `bot.globals` | the two global pages, from krkn-hub root `env.sh` + krkn |
| `operator` | `bot.operator` | all 9 CRDs at once |

Targets must match `a-z0-9-`. Anything else is rejected before any work happens.

### Three ways to fire it

| Method | How | Targets |
| --- | --- | --- |
| Automatic | Push to a source repo's default branch on a watched path | Derived by that repo's trigger |
| Manual | Actions -> Doc Sync -> Run workflow, `scenarios` input | **Space-separated, several at once**: `node-scenarios globals operator` |
| Comment | `/fix <target> [<target>...]` on any issue or PR | The rest of the first line |
| Comment | `/resync` on a bot PR | Derived from the files that PR already changed |

Manual dispatch is how we switch repos by hand. To regenerate everything the bot
covers, one run does it:

```
scenarios: globals operator <each scenario you care about>
```

### How `/resync` picks targets

`bot.targets` maps the website paths a PR changed back to the target that
regenerates them. It runs in the workflow as one pipe, so the rule lives in the
package and is unit-tested rather than written twice in shell:

```bash
gh api "repos/$REPO/pulls/$PR_NUMBER/files" --jq '.[].filename' | python3 -m bot.targets --website .
```

| Changed path | Target |
| --- | --- |
| `data/params/globals/**` | `globals` |
| `data/params/<crd plural>/**` | `operator` |
| `data/krkn_operator_crds.yaml`, `content/en/docs/krkn-operator/api-reference/**` | `operator` |
| `data/params/<anything else>/**` | that scenario |

The CRD plurals are read from `data/krkn_operator_crds.yaml`, the index the bot
itself writes, so nothing is guessed. Without that file every group resolves to
itself, which is the pre-operator behaviour.

This matters because the two segments of `data/params/<group>/<table>.yaml` mean
different things per source: for krkn-operator the group is a CRD plural, and only
`bot.operator` can regenerate it.

**We cannot test `/resync` on a fork.** A fork PR gets no secrets, so this is the
one path that has to be right by construction. That is why it moved out of the
workflow's shell and into the package.

### Adding a fourth source repo later

1. Add a `<repo>-template/` with a trigger watching the right paths and dispatching a new target name
2. Add a clone step and a `case` branch for that target in `doc-sync.md`
3. `gh aw compile`, commit both files
4. Install the App on the new repo, and set `APP_ID` and `APP_PRIVATE_KEY` there

&ensp;

## 4. Org setup

### 4a. Who can do each step

Worth checking before starting, because these sit with different people in most
orgs and a missing one blocks the whole setup.

| Step | Needs | If we do not have it |
| --- | --- | --- |
| Create the GitHub App | **Org owner** | Ask an owner. A personal App works for testing but is owned by a person, not the project |
| Install the App on the four repos | Org owner, or repo admin if the org allows it | Ask an owner |
| Set repo secrets and variables | **Repo admin** on each repo | Ask the repo's admin, or use org-level secrets below |
| Merge the four PRs | Repo write plus review approval | Normal contribution flow |
| Run `/fix` once live | A role in `roles:` | Widen the list, or dispatch manually |

An App owned by the org survives a maintainer leaving. An App owned by an
individual does not, so make the org own it before handover.

### 4b. The GitHub App

The bot needs its own identity so PRs are authored by the app, not by
`github-actions[bot]`. Workflows mint a short-lived token from the app id and
private key.

1. Org **Settings -> Developer settings -> GitHub Apps -> New GitHub App**
2. Name it. Uncheck **Webhook -> Active**, it only mints tokens
3. Set the permissions below. Install target **Only on this account**
4. Create it, note the **App ID**
5. **Generate a private key**. The `.pem` downloads once. Never commit or paste it
6. **Install** on `website`, `krkn-hub`, `krkn` and `krkn-operator`, using **Only select repositories**

| Permission | Level | Why |
| --- | --- | --- |
| Metadata | Read | Needed by almost every repo API call |
| Contents | Read and write | Push the branch, create commits |
| Pull requests | Read and write | Open and edit the draft PR |
| Issues | Read and write | Create and edit the rolling drift issue |
| Actions | Read and write | Dispatch a workflow via the API |

Skip **Workflows**. The bot never writes under `.github/workflows/`.

A missed install shows up later as a 403, not at setup time.

### 4c. Secrets and variables

**Settings -> Secrets and variables -> Actions**, per repo. Variables and secrets
are separate tabs, and `vars.X` will not read a secret.

| Repo | Name | Type |
| --- | --- | --- |
| website | `APP_ID` | **variable** |
| website | `APP_PRIVATE_KEY` | secret |
| website | `LLM_API_KEY` | secret |
| krkn-hub, krkn, krkn-operator | `APP_ID` | **secret** |
| krkn-hub, krkn, krkn-operator | `APP_PRIVATE_KEY` | secret |

`APP_ID` is a variable on the website and a secret on the sources. Same value, two
ways of reading it, because that is how the templates reference it.

**`LLM_API_KEY` is the only model credential**, and only the website needs it. If
we later point the engine at a custom provider it reuses the same key, so there is
still only one to rotate.

**Set the two shared secrets once at org level.** Org **Settings -> Secrets and
variables -> Actions -> New organization secret**, with a repository access policy
listing the four repos. That saves four copies of `APP_PRIVATE_KEY` and makes
rotation one edit. `APP_ID` still has to be a repo **variable** on the website,
because an org secret cannot be read as `vars.APP_ID`.

Worth knowing:

- The App token and the model key are unrelated. Neither substitutes for the other.
- `LLM_API_KEY` is only checked for being non-empty. A wrong key fails at call time, not at startup.
- If it is missing, descriptions go blank and the run still passes. Read the gap table in the commit message.
- `APP_PRIVATE_KEY` is not in the log redaction list. Be careful what gets printed.

&ensp;

## 5. The four PRs

One per repo, each from a template folder in `docsync-bot`.

| PR against | Template | Files it adds |
| --- | --- | --- |
| website | `website-template/` | `doc-sync.md`, `drift-report.yml`, `hugo-build.yml`, `layouts/shortcodes/param-table.html`, `layouts/shortcodes/crd-ref.html`, `examples/data/params/**` |
| krkn-hub | `krkn-hub-template/` | `.github/workflows/trigger-docs-sync.yml` |
| krkn | `krkn-template/` | `.github/workflows/trigger-docs-sync.yml` |
| krkn-operator | `krkn-operator-template/` | `.github/workflows/trigger-docs-sync.yml` |

### Change these before opening them

`doc-sync.md` now ships production-ready: both `target-repo` keys name
`krkn-chaos/website`, `roles` is `[admin, maintainer, write]`, the describer env
is wired and all three sources are cloned. Two things are still ours to set:

1. `krkn-template/` and `krkn-hub-template/` -> `owner: krkn-chaos`, `repositories: website`, `--repo krkn-chaos/website`. The krkn-operator template already points at production
2. Pick the describer endpoint: `LLM_BASE_URL` and `LLM_MODEL` on the generation step, and put the key in `LLM_API_KEY`. See [section 6](#6-the-engine)

### Always recompile the lock

- `doc-sync.md` is source. Actions runs `doc-sync.lock.yml`.
- After **any** edit to the `.md`, run `gh aw compile` and commit both files.
- Hand-editing the lock does not work. gh-aw checks it at runtime and fails.

### Nothing runs until they merge

- A workflow only fires from the **default branch**.
- A PR from a fork gets **no secrets**.

So the triggers stay quiet on the PRs themselves. Expected, not broken.

&ensp;

## 6. The engine

**Pick a model whose name matches `copilot/*`, `anthropic/*`, `openai/*`,
`google/*` or `gemini/*`.**

gh-aw puts an api-proxy between the agent container and the provider, and that
proxy steers the model **before the request leaves the runner**. A model outside
those globs is refused with a bare 400 that names no cause. We lost eight runs to
this.

### The three paths

| Path | Verdict |
| --- | --- |
| Supported vendor, no BYOK. `engine: {id: copilot, model: gpt-4o-mini}` | **Recommended.** Steering resolves against a provisioned provider, so the gate never fires. This is what the template ships |
| BYOK to another provider, naming an allowlisted model | Works, we proved it on NVIDIA NIM, but it needs two workarounds of our own and the agent still cannot call a tool |
| Upgrade gh-aw to v0.84.4 and set `sandbox.agent.token-steering: false` | The documented remedy. **We have not tested it** |

We pin gh-aw at **v0.80.9** in `.github/aw/actions-lock.json`.

We went down the BYOK path, proved it, then came back. On the revert to Copilot
all six jobs ran green **and the agent opened the PR itself**, which is the
evidence that tool definitions are back and both BYOK workarounds are optional.
The NVIDIA configuration is not deleted: it sits commented in our fork's
`doc-sync.md` under three blocks headed `NVIDIA PATH n of 3`, so swapping back is
uncommenting three blocks. The shipped template carries none of it.

### What went wrong, so nobody repeats it

Tracked upstream as [github/gh-aw#50113](https://github.com/github/gh-aw/issues/50113),
open since 2026-08-03 and untouched since 2026-08-04. Its Case 2 is our engine and
mode.

| Finding | Evidence |
| --- | --- |
| The proxy rejects an unlisted model locally, in about 90ms, with no error body | The provider never saw the request. Replaying the captured 60,619-byte request straight at the provider returned 200 |
| The allowlist has no vendor beyond those five globs | `modelAliases.any -> [copilot/*, anthropic/*, openai/*, google/*, gemini/*]` |
| `COPILOT_PROVIDER_MODEL_ID` does not rescue it on 0.80.9 | The wire model stayed unchanged and the provider 404'd |
| **In BYOK mode Copilot CLI sends no tool definitions at all** | Its own `Wire request` log across five runs. Wire keys were only `[messages, model, stream, stream_options]` |
| `engine: codex` is not an escape hatch | Codex CLI dropped `chat/completions` in February 2026 and needs `wire_api = "responses"`, which gh-aw cannot set |

Two rules we now follow:

- **Read the gh-aw docs at the tag you run, not at `main`.** Two of the three knobs we found on `main` do not exist in 0.80.9: `token-steering` shipped in v0.84.4, and `model-fallback` is unreleased in every version.
- **Do not depend on the agent calling a safe-output tool** if there is any chance of BYOK. Write the NDJSON item from a deterministic step instead, and write the patch too: gh-aw needs both, and it only produces the patch when the agent step succeeds.

### If we do use BYOK anyway

gh-aw treats three variables specially, which is why BYOK is the least bad custom
path:

| Variable | Behaviour |
| --- | --- |
| `COPILOT_PROVIDER_BASE_URL` | Activates BYOK, and gh-aw adds the hostname to the firewall allow-list automatically |
| `COPILOT_PROVIDER_API_KEY` | A sanctioned `${{ secrets.* }}` exception under strict mode, and stripped from the agent container |
| `COPILOT_PROVIDER_BEARER_TOKEN` | Same treatment |
| `COPILOT_PROVIDER_TYPE` | The wire dialect, `openai` for anything OpenAI-compatible. Not special-cased by gh-aw, it is passed to Copilot CLI |

The model name still has to satisfy the proxy allowlist **and** be one the
provider hosts. Only two of NVIDIA's whole catalog clear the proxy:
`openai/gpt-oss-20b`, which is what we proved, and `openai/gpt-oss-120b`, which
gave transient key errors, took 171s per call on the free tier and hit
`ECONNRESET` at 290s.

Strict mode is mandatory on public repos, and `krkn-chaos/website` is public.

The full investigation, all eight runs, is
[docsync-bot#24](https://github.com/krkn-chaos/docsync-bot/issues/24). Its
evidence chain, which we re-verified:
[krkn-hub#61](https://github.com/StrikerEureka34/krkn-hub/pull/61) merged
07:27:57Z carrying a parameter nothing described, run **32006043805** at 07:30 on
the NIM env, and [website_2#86](https://github.com/StrikerEureka34/website_2/pull/86)
with exactly one `description_source: llm` row. The trigger was built so the
model was the only thing that could have filled it.

### Telling a dead key from a quiet one

A bad `LLM_API_KEY` fails the same way a missing one does, by design: the run
stays green and the cells come out blank. So **"the run passed" is not the
acceptance check**.

| Where to look | What a working key shows | What a dead one shows |
| --- | --- | --- |
| The gap table in the commit message | rows sourced `llm` | `model unavailable: endpoint returned HTTP 401: ...` |

Check that after setting the secret, and after any provider change. Ours is
invalid at the time of writing, so it needs revalidating before the describer is
relied on.

### Threat detection

It is a second model call, roughly 68k tokens, that scans the agent's output and
**reuses whatever engine the workflow uses**. On a supported vendor, leave it on.
Turn it off only if the provider cannot take the load, and note the key sits under
`safe-outputs`, not under `create-pull-request`:

```yaml
safe-outputs:
  threat-detection: false
```

The deterministic steps and `safe-outputs` still bound what the agent can do.

### Running with no inference

Descriptions are the only thing a model ever writes, so the pipeline can run
fully deterministically and keep every gh-aw feature.

To turn inference off, in `doc-sync.md`:

| Toggle | Effect |
| --- | --- |
| Leave `LLM_API_KEY` unset, or omit the describer env entirely | No description call. Every other rung still fires |
| `safe-outputs: threat-detection: false` | Drops the `detection` job from the compiled workflow |
| `max-turns: 1` | Caps the agent, whose output we do not read |

**The agent job cannot be removed.** gh-aw compiles five jobs, `pre_activation`,
`activation`, `agent`, `detection` and `conclusion`, and only `detection` is
optional. There is no non-model mode.

On a supported vendor the agent does call the safe-output tool, so it is what
opens the PR and that is fine: it reads nothing and writes a fixed body. To make
even that non-load-bearing, a deterministic step can write the
`create_pull_request` NDJSON item and the `git format-patch` output itself, before
the agent runs. gh-aw needs both. That step exists commented in our fork's
`doc-sync.md` as `NVIDIA PATH 3 of 3`, written for BYOK where the agent cannot
call a tool at all, and it works just as well as a belt-and-braces measure.

| | Cost |
| --- | --- |
| Kept | Every rung except the model, so source comments, published tables, the previous file and cross-source borrows all still fill cells |
| Kept | All gh-aw features below, unchanged |
| Lost | Only parameters that no source describes and no page ever described. Each one is listed in the gap table rather than guessed at |
| Remaining spend | One short agent call per run, whose output is discarded |

The krkn-operator source already runs this way permanently: every CRD field
carries its Go doc comment, so that target never reaches the model.

&ensp;

## 7. gh-aw features we use

All of these are configured in `doc-sync.md` and take effect only after
`gh aw compile`. The compiled `doc-sync.lock.yml` is what Actions runs.

| Feature | What it gives us | Where to change it |
| --- | --- | --- |
| `on.slash_command` | `/fix` and `/resync` as ChatOps entry points | `on: slash_command: name: [fix, resync]` |
| `on.roles` | Only listed roles can drive the bot by comment | `roles: [admin, maintainer, write]` |
| `on.bots` | Lets our own app's comments trigger it, without opening it to all bots | `bots: [krkn-docs-bot]` |
| `permissions` | The workflow token is read-only. Writes happen through the app token instead | `permissions: read-all` |
| `steps` | Our deterministic work, run **before** the agent and before the firewall | the `steps:` block |
| `engine` | Which model the agent uses, and BYOK if set | the `engine:` block, see [section 6](#6-the-engine) |
| `tools` | What the agent may call. **We declare none**, because opening a PR is a safe output and needs no tool. `tools: bash: ["*"]` appears only in the commented BYOK block | the `tools:` block, absent by design |
| `network.allowed` | An egress firewall around the agent. BYOK hosts are added automatically | `network: allowed:` |
| `max-turns`, `timeout-minutes` | Hard caps on agent cost and runtime | top level |
| `safe-outputs.github-app` | Mints the short-lived app token, so PRs carry the bot identity | `app-id`, `private-key` |
| `safe-outputs.create-pull-request` | Opens the PR as a draft, prefixed, capped at one, against a named repo | `draft`, `title-prefix`, `max`, `target-repo` |
| `safe-outputs.push-to-pull-request-branch` | Lets `/resync` update an existing PR instead of opening another | `target-repo` |
| `safe-outputs.threat-detection` | A model scan of the agent's output | `threat-detection: false` to drop the job |
| Generated concurrency | One in-flight run per issue or PR, so two merges cannot race | Automatic, no setting |
| Secret redaction | Named secrets masked in logs, and stripped from the agent container | Automatic, via `GH_AW_SECRET_NAMES` and `--exclude-env` |
| Lock integrity | A hand-edited lock fails at runtime | Automatic. Always `gh aw compile` |

Two things worth remembering:

- Anything in `steps:` runs before the firewall exists, so it needs no `network.allowed` entry. This is why the describer works without one.
- A safe-output written from `post-steps:` is **too late**. Those compile in after the step that reads the file. Write from `steps:`.

&ensp;

## 8. The workflows

| Workflow | Repo | Trigger | Model needed |
| --- | --- | --- | --- |
| `trigger-docs-sync.yml` | krkn-hub, krkn, krkn-operator | `push` to the default branch on the watched paths | No |
| `doc-sync.md` -> `.lock.yml` | website | `/fix`, `/resync`, `workflow_dispatch` | Yes, both calls |
| `drift-report.yml` | website | weekly | **No.** Plain workflow, report only, writes no files. Scans all three sources |
| `hugo-build.yml` | website | pull request | No |

Watched paths, per trigger:

| Repo | Paths | Dispatches |
| --- | --- | --- |
| krkn-hub | `env.sh`, `*/env.sh`, `*/krknctl-input.json` | the scenario names, or `globals` for the root file |
| krkn | `containers/krknctl-input.json` | `globals` |
| krkn-operator | `config/crd/bases/**` | `operator` |

`push` rather than `pull_request` is deliberate: a PR from a fork gets no
repository secrets, so the token step would fail on exactly the contributions that
matter. A merge produces a push either way.

### Gaps to close in the shipped template

`website-template/doc-sync.md` now matches the workflow we tested: three clones,
three target shapes, `bot.targets` for `/resync`, the gap report in the commit
message, and production `roles` and `target-repo`. One gap is left:

| Gap | Consequence |
| --- | --- |
| `krkn-hub-template/` and `krkn-template/` still dispatch to a fork | Those two triggers would fire at the wrong website. The krkn-operator trigger already names production |

### It ships as two PRs

The operator coverage and the choice of inference endpoint are separate
decisions, so they are separate reviews:

| PR | Contains |
| --- | --- |
| `feat/krkn-operator-source` | The source itself: the CRD parser, the generator, the drift coverage, the trigger, the shortcode, and the workflow's three clones and target routing. **No `LLM_*` at all**, which is safe because the operator target never calls the model |
| `fix/describer-config` | The describer: `LLM_*` wired to NVIDIA NIM with Copilot commented beside it, `_TIMEOUT` reading `LLM_TIMEOUT` with a 120s default, and a refusal to send the key over plaintext |

### The model key follows the endpoint

`LLM_API_KEY` is the only model credential, but **what it has to be, and what it
is worth to an attacker, depends entirely on `LLM_BASE_URL`**:

| Endpoint | The key is | Blast radius if leaked |
| --- | --- | --- |
| An inference provider, the shipped default | an inference key | That provider's quota. No repo write, no GitHub scope |
| `https://api.githubcopilot.com` | a GitHub token with Copilot access | **A GitHub credential.** Whatever that token can do |

We hit this ourselves: the deployed lock on the fork reads
`LLM_API_KEY: ${{ secrets.COPILOT_GITHUB_TOKEN }}`, so on that deployment the
"model key" is a GitHub token. Shipping NVIDIA as the default is what makes the
one-credential story true rather than merely tidy.

`LLM_BASE_URL` must be `https`. The key travels on it as a bearer header, so
`describe.py` refuses a plaintext base rather than sending it.

`_TIMEOUT` reads `LLM_TIMEOUT`, default 120s, because the same prompt measured
20.6s, 27.4s and 83.3s within one hour on a free tier and the old hardcoded 30s
cut the slow end off.

The describer env now ships as the combination we ran green:

```yaml
env:
  LLM_BASE_URL: https://api.githubcopilot.com
  LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
  LLM_MODEL: gpt-4o
```

Swap all three for any OpenAI-compatible endpoint. All three also have built-in
defaults, so **deleting them is legal and silent**: the built-in host measured
unreachable from GitHub Actions on 2026-08-13, port 443 filtered for GitHub's
egress ranges, which leaves every generated description blank while the run stays
green.

&ensp;

### Reading the drift issue

One rolling issue, rewritten in place every week. It opens collapsed into three
groups, so the whole report is three lines until something is expanded:

```
<details><summary><b>krkn-hub scenarios</b> (26)</summary>
<details><summary><b>Global parameters</b> (1)</summary>
<details><summary><b>krkn-operator CRDs</b> (9)</summary>
```

A group whose items need a person says so in the header, so nothing important
hides behind the collapse:

```
▸ krkn-operator CRDs (9) · 🔴 1 needs a maintainer
```

Inside a group, one checkbox per scenario or CRD, which is the unit `/fix` acts
on, and a nested `<details>` holding the per-source finding tables. A tick is
matched against the finding text, so it survives only while that finding is
unchanged: new drift cannot hide behind a box someone already ticked.

Every item lands at one of three levels. Nothing is marked when `/fix` simply
does it, and the marker is never generic:

| Marker | Meaning |
| --- | --- |
| none | `/fix` regenerates it from source |
| `⚠️ **Review first:**` | `/fix` does it, but it deletes a documented row |
| `🔴 **Maintainer needed:**` | `/fix` provably cannot, and the text names why for that item |

| Finding | Command |
| --- | --- |
| `missing-table`, `missing`, `stale` | `/fix <scenario>`, `/fix globals`, `/fix operator` |
| `missing-link` | `/fix operator`. It adds the `crd-ref` call itself |
| `extra` | The same command, but it **deletes a documented row**, so read the table first |
| `unlinked` | **None**, and the item says which of three jobs it is: the kind is unmapped, its page does not exist, or that page already carries a `crd-ref` |

Two deliberate choices here:

- **One `/fix operator` covers every CRD.** Regeneration is idempotent and git stages only real changes, so a per-CRD target would produce an identical diff through a second code path.
- **`missing-link` and `unlinked` are separate on purpose.** They looked identical until 2026-08-18, and the report told maintainers to hand-edit `_PAGE_LINKS` for all nine CRDs while `link_pages` was about to add every one of those links by itself.

### What the bot will not do about links

`link_blocker` in `bot/operator.py` answers "will `link_pages` link this kind",
sharing its predicate with `link_pages` so the report cannot promise a link
nothing writes. What is left over is genuinely a person's call:

| Human error | Caught by | Result |
| --- | --- | --- |
| A kind that does not exist, `crd="krknuser"` | `crd-ref.html` calls `errorf` against the generated index | **Hugo Build Check fails the PR** |
| A CRD later renamed or deleted, link left behind | The same gate, once the index regenerates | Red build |
| Only one of a page's two kinds linked by hand | `link_blocker` | Reported, naming that cause |
| A link on a page that does not describe that kind | Nothing | **Not detected.** A `crd-ref` anywhere counts. `link_pages` still writes the mapped page, so the cost is a stray link, not a broken one |

That last row is deliberate. Requiring the link to sit on the mapped page would
treat the bot's hardcoded `_PAGE_LINKS` guess as more authoritative than a
maintainer's judgement, which is the opposite of why `unlinked` refuses to guess.

&ensp;

## 9. Verify

1. Push to a source repo's default branch touching a watched path
2. The trigger mints an app token scoped to the website
3. It runs `gh workflow run doc-sync.lock.yml` on the website
4. The bot regenerates, branches, commits and opens a draft PR
5. `Hugo Build Check` runs on that PR

What to check:

- The source repo's Actions tab prints the target names it found
- The PR is authored by the app, not `github-actions[bot]`
- **Hugo Build Check passes.** A PR appearing is not success on its own
- The commit message's gap table has no unexpected `llm` or blank rows

Also worth one manual run each: `drift-report.yml`, and a `/fix <scenario>`
comment.

&ensp;

## 10. Troubleshooting

Symptom -> cause -> fix.

### Model

- Descriptions blank, run green -> `LLM_API_KEY` missing or wrong, or `LLM_BASE_URL` unreachable -> set them. Nothing validates beyond non-empty
- Engine returns 400 in about 90ms with no body -> the model name is outside the proxy allowlist -> name a `copilot/*`, `anthropic/*`, `openai/*`, `google/*` or `gemini/*` model
- Engine returns 404 from the provider -> the proxy rewrote the model to one the provider does not host -> name a model the provider actually serves
- The agent never calls the safe-output tool -> BYOK sends no tool definitions -> write the item from a deterministic step
- Compile fails on `domain pattern contains invalid character ':'` -> a port in `network.allowed` -> serve on 443
- Compile rejects `token-steering` or `model-fallback` -> the release predates them -> upgrade, or use an allowlisted model

### gh-aw

- `ERR_CONFIG: Lock file is outdated!` -> the `.md` was edited without recompiling -> `gh aw compile`, commit both
- The workflow still does the old thing after an edit -> same cause
- `/fix` shows `skipped` -> the activation gate -> `/fix <scenario>` must be the first text in the comment, and the commenter needs an allowed role
- A safe-output write has no effect -> it was in `post-steps:`, which compiles in **after** the ingest reads the file -> move it into `steps:`

### Targets

- A target is rejected before any work -> it has a character outside `a-z0-9-` -> check for a stray quote or capital
- `/resync` finds no targets -> the PR changed nothing under `data/params/`, `data/krkn_operator_crds.yaml` or the api-reference pages -> name the target with `/fix` instead
- `/resync` on an operator PR runs `bot.doc_bot` -> the deployed lock predates `bot.targets`, or `data/krkn_operator_crds.yaml` is missing from the checkout -> recompile, and check the index exists
- A scenario runs but writes nothing -> the website has no page carrying that scenario's marker -> add the page first
- A CRD's page never gets linked -> read the item. `missing-link` means `/fix operator` does it; `unlinked` names which of the three human jobs it is
- A kind stays `unlinked` after adding a `crd-ref` to its page -> the call went on a page `_PAGE_LINKS` does not map to that kind -> the scan counts it as linked; check the mapped page instead

### Actions and permissions

- `gh workflow run` does nothing -> `workflow_dispatch` only runs a file on the default branch -> merge it first
- Secrets empty in a run -> the run came from a fork `pull_request` event -> trigger on `push`
- Cross-repo dispatch fails -> `GITHUB_TOKEN` is scoped to its own repo -> mint an App token for the target
- Dispatch returns 403 despite the App being installed -> missing **Actions: write** -> add it
- An org secret is set but empty in the run -> its repository access policy does not list that repo -> add it
- PR authored by `github-actions[bot]` -> the step used the default token -> pass the minted app token

&ensp;

## Sources

- gh-aw: [engines](https://github.github.com/gh-aw/reference/engines/), [network](https://github.github.com/gh-aw/reference/network/), [safe outputs](https://github.github.com/gh-aw/reference/safe-outputs/), [threat detection](https://github.github.com/gh-aw/reference/threat-detection/)
- The steering blocker: [github/gh-aw#50113](https://github.com/github/gh-aw/issues/50113)
- Codex dropping chat/completions: [openai/codex#7782](https://github.com/openai/codex/discussions/7782)
- [`create-github-app-token`](https://github.com/actions/create-github-app-token)
- [App permissions reference](https://docs.github.com/en/rest/authentication/permissions-required-for-github-apps)
- Our BYOK investigation, filed: [docsync-bot#24](https://github.com/krkn-chaos/docsync-bot/issues/24), with the working notes in [2026-08-17-nvidia-nim-engine-check.md](2026-08-17-nvidia-nim-engine-check.md)
