# krkn-docs-bot (gh-aw edition) — Build Journal

A working log of what we built, why, and every wall we hit along the way.
Written so a mentor can read it top to bottom and understand both the design
and the detours. Dates are 2026.

---

## TL;DR (read this first)

- **What:** an automated documentation-sync pipeline for krkn-chaos. When a
  chaos scenario's parameters change in `krkn-hub`, a bot regenerates the
  parameter tables on the docs website and opens a draft PR.
- **How:** a small deterministic Python package (`krkn-docs-bot-gh-aw`) driven
  by a **GitHub Agentic Workflow (gh-aw)** running on the **GitHub Copilot**
  engine (zero LLM cost on a Student subscription).
- **Where it stands now:** the **entire pipeline runs green** — gating, the
  Copilot agent, three layers of authentication, the GitHub App token mint, and
  the safe-output plumbing all work. The last run ended in a **no-op** because
  of a single relative-path ambiguity in the prompt (the bot wrote the YAML to
  the workspace root; the agent looked for it inside the cloned `krkn-hub/`
  folder). That is a one-line fix, not a design flaw.
- **What we want next:** a **Red Hat / "normal mode" LLM API key** so we can run
  the agent on a standard API engine and test frequently without the limits and
  account-coupling of the Copilot Student path.

---

## Why this project exists

krkn-chaos scenarios are configured through bash environment variables in
`krkn-hub` (each scenario has an `env.sh` and sometimes a `krknctl-input.json`).
The docs website documents those same parameters in Markdown tables, by hand.
The two drift apart: a new variable lands in `env.sh`, nobody updates the table,
and the docs silently go stale.

The bot closes that loop: it reads the source of truth (`env.sh`), generates a
structured data file the website renders, and replaces the hand-maintained
Markdown table with a shortcode that renders from that data. A human still
reviews the result (it lands as a **draft PR**), but the drudgery is automated.

---

## The three repositories and why each is separate

| Repo | What it is | Role in the pipeline | Why it has to be its own repo |
|------|-----------|----------------------|-------------------------------|
| **`StrikerEureka34/krkn-docs-bot-gh-aw`** | The bot package + the workflow **source**. | Holds the Python code and the authored `doc-sync.md` (gh-aw workflow). Compiled to a `.lock.yml`. Released as pip-installable tags. | This is *our* code. Keeping it standalone lets the bot be `pip install`-ed by any workflow and versioned with tags. |
| **`StrikerEureka34/website_2`** | A fork of `krkn-chaos/website` (the Hugo docs site). | The workflow is **deployed** here (the compiled lock + the prompt), it runs on **this repo's Actions**, and draft PRs **land here**. | A gh-aw workflow must live in the repo whose Actions runner executes it. The site is also the target of the change, so this is both the runner and the destination. |
| **`StrikerEureka34/krkn-hub`** | A fork of `krkn-chaos/krkn-hub` (source of truth for scenario env vars). | Holds the scenario `env.sh` files **and** the dispatcher workflow `trigger-docs-sync.yml`. A merged PR here simulates an upstream parameter change and kicks off a sync. | It is the data source. The fork stands in for upstream so our test changes are visible and merge-able without touching the real project. |

> The fork-of-a-fork setup is deliberate: it lets us exercise the *real*
> upstream content and the *real* trigger path end to end, in accounts we
> control, without proposing anything to krkn-chaos until it actually works.

---

## How the pipeline flows (one sentence per hop)

1. A PR merges into **`krkn-hub`** (fork `main`).
2. **`trigger-docs-sync.yml`** fires on that push, mints a GitHub App token, and
   sends a `repository_dispatch` to **`website_2`**.
3. **`doc-sync.lock.yml`** activates on `website_2`; the **Copilot agent** runs.
4. The agent: `pip install` the bot at a pinned tag → `git clone` krkn-hub →
   run `bot.doc_bot --scaffold` → improve the generated descriptions → declare a
   **`create-pull-request`** safe-output.
5. gh-aw's **safe_outputs** job mints the App token again and opens a **draft
   PR** on `website_2` with the regenerated data file and the shortcode-injected
   tab page.

See `PIPELINE_OVERVIEW.md` for the per-job, runner-level breakdown.

---

## The detours (everything that sidetracked us, in order)

Each of these cost real time. They are listed so the pattern is visible: almost
every wall was an **integration/auth/environment** issue, not a logic bug in the
bot.

### 1. The `:free` model and rate limits
Early on (OpenRouter path) we used a free model tier
(`nvidia/nemotron-3-nano-...:free`). Free tiers rate-limit aggressively and
return non-deterministic JSON, which made runs flaky and slow to debug.

### 2. Codex engine + OpenRouter burned real money
We ran the gh-aw **codex** engine against OpenRouter's `gpt-oss-120b`. It
requested **65,536 tokens per turn**, and across retries it burned through
roughly **$1 of credit** and then hit **HTTP 402 Payment Required**.
**Fix:** switched the engine to **`copilot`**, which uses the GitHub Copilot
Student subscription at **zero marginal cost**.

### 3. Bare Markdown tables weren't detected
krkn-chaos parameter tables are written **without leading pipes**
(`Param | Desc` and `--- | ---`, not `| Param | Desc |`). Our shortcode injector
only recognized the leading-pipe style, so it silently did nothing.
**Fix:** strip pipes before classifying a separator row; rework header/end
detection. Made idempotent (re-running never double-injects).

### 4. The bot actor was blocked at the gate
gh-aw's `pre_activation` job gates who may trigger a workflow. `roles:` only
covers human actors; a GitHub **App** actor is rejected unless it is explicitly
allow-listed.
**Fix:** add `on.bots: [krkn-docs-bot]` to the workflow.

### 5. Three identities, and the confusion between them
This was the deepest rabbit hole. The pipeline uses **three separate
credentials**, and mixing them up produced a string of auth errors:

| Identity | Used for | Supplied by |
|----------|----------|-------------|
| **Copilot inference** | the agent's own reasoning (the LLM engine) | `COPILOT_GITHUB_TOKEN` (a **fine-grained PAT**) |
| **File operations** | git/file work inside the agent sandbox | `GITHUB_TOKEN` (auto-injected by Actions) |
| **PR creation** | writing the draft PR to `website_2` | a **GitHub App token** minted from `APP_ID` + `APP_PRIVATE_KEY` |

Sub-problems within this:
- **`APP_ID` as a secret vs a variable.** The workflow reads `vars.APP_ID`, so
  `APP_ID` must be an Actions **Variable**, not a Secret.
- **Classic PAT rejected.** Copilot does not accept classic `ghp_...` tokens;
  it requires a **fine-grained** PAT.
- **Wrong fine-grained permission.** We first granted `Copilot Chat`
  (for reading session messages) and got 401s. The correct permission for
  inference is **`Copilot Requests: Read-only`**.

### 6. HTTP 422 on the App-token mint
The `create-pull-request` safe-output asks for an installation token scoped to
specific permissions. The mint failed with **422 "permissions requested are not
granted to this installation."** We initially mis-diagnosed this as a stale lock
/ leftover `labels:` config. The real cause: the **GitHub App installation** was
missing **Issues** and **Administration**. gh-aw's `create-pull-request`
*always* requests `issues: write` (a PR is an issue under the API) and
`administration: read` (cross-repo target inspection).
**Fix:** grant the App **Issues: read/write** and **Administration: read**, then
**re-accept** the updated permissions on the installation. (Confirmed by reading
the `permission-*` lines in the compiled lock and diffing against the
installation's granted set.)

### 7. The `jiter` / `openai` install failure
With auth finally working, the bot's `pip install` aborted with a
"network-related error during metadata generation" on **`jiter`**. Chain:
`openai` SDK → depends on `jiter` (a **Rust** JSON parser) → no usable wheel →
pip builds the sdist → the build shells out to **crates.io** for metadata →
the gh-aw **firewall sandbox blocks crates.io** → build fails → install aborts.
**Fix:** the bot only ever made a single chat-completions call, so we replaced
the entire `openai` SDK with **stdlib `urllib`**. No Rust, no crates.io, ~40 MB
of transitive dependencies gone. (Later removed entirely — see #9.)

### 8. HTTP 401 from GitHub Models
The bot's own LLM call (to write parameter descriptions) hit
`models.inference.ai.azure.com` and got **401 Unauthorized**. The 401 (not a
connection error) proved the request *reached* the service and was rejected on
auth: the Actions `GITHUB_TOKEN` **cannot** call GitHub Models — that needs a
user PAT with `Models: read`. The bot had no valid Models credential.

### 9. The architecture correction (the right call)
Problem #8 forced a good question: *why does the bot call a second LLM at all,
when the gh-aw agent is already an LLM sitting right there?* That was an
over-build — an LLM shelling out to a script that calls another LLM, each with
its own auth.
**Decision:** the **Copilot agent writes the descriptions**; the bot goes back
to being **purely deterministic** (parse → emit YAML → inject shortcode). It
emits a placeholder (`Configures <param>.`) only for new/changed params, and the
agent rewrites just those placeholders. This **deleted** `llm_client.py`, the
`openai` dependency, the second token, and the `models.inference` host all at
once.

### 10. The final no-op (current open item)
Full pipeline green, but the last run produced **no PR**. Root cause: a
**relative-path mismatch**. The bot writes the data file to `WEBSITE_ROOT`
(default `.` = the website_2 workspace root): `./data/params/<scenario>/...`.
The agent, however, searched **inside the cloned hub** —
`glob(krkn-hub/data/params/node-scenarios/*.yaml)` — found nothing, and
correctly emitted a `noop` ("No YAML files were generated") rather than open an
empty PR. The prompt never told the agent where the output actually lands.
**Fix (next):** anchor the output path in the prompt (and/or set `WEBSITE_ROOT`
explicitly) so the agent looks in the workspace root, not the hub clone.

---

## Cheat-sheet: what changed in each repo and why

### `krkn-docs-bot-gh-aw` (our package + workflow source)
| Change | Why |
|--------|-----|
| `bot/scaffold.py` — bare-table detection + idempotent shortcode injection | krkn-chaos tables have no leading pipes; never double-inject |
| `bot/llm_client.py` — created (urllib), then **deleted** | replaced `openai` to dodge `jiter`; then removed once the agent took over descriptions |
| `bot/doc_bot.py` — deterministic descriptions (`_no_descriptions`), placeholder fallback | bot no longer calls an LLM; agent fills new-param descriptions |
| `pyproject.toml` / `requirements.txt` — dropped `openai` | kills the Rust/`jiter` build in the firewall sandbox |
| `.github/workflows/doc-sync.md` — engine `codex`→`copilot`; add `on.bots`; remove `labels`; tune network allowlist; add scaffold + description-writing prompt steps; strip LLM env; bump pinned pip tag | cost, gating, App-token scope, and the description-ownership change |
| Tags `v0.1.0` → `v0.1.6` | each fix shipped as a pinned release the workflow installs |
| 59 tests passing | scaffold idempotency, bare-table cases, deterministic emit |

### `website_2` (fork of krkn-chaos/website — runner + PR target)
| Change | Why |
|--------|-----|
| `.github/workflows/doc-sync.lock.yml` + `doc-sync.md` deployed (and re-deployed per version) | the workflow must live where it runs; the `.md` is **runtime-imported** by the lock, so both files ship together |
| Variable `APP_ID` | workflow reads `vars.APP_ID` |
| Secrets `APP_PRIVATE_KEY`, `COPILOT_GITHUB_TOKEN` | App-token mint; Copilot inference (fine-grained PAT, `Copilot Requests: Read-only`) |
| GitHub App **krkn-docs-bot** granted Contents, Pull requests, Issues, Administration, Actions; installation re-accepted | satisfy the `create-pull-request` token scope (fixes the 422) |

### `krkn-hub` (fork of krkn-chaos/krkn-hub — data source + trigger)
| Change | Why |
|--------|-----|
| `.github/workflows/trigger-docs-sync.yml` | dispatches the sync to `website_2` on merge |
| `node-scenarios/env.sh` — test params `RETRY_WAIT`, `RETRY_COUNT`, `MAX_NODES_AFFECTED` (PRs #24, #25, #26) | each PR simulates an upstream change to trigger and exercise the pipeline |

---

## What we achieved

- A **complete gh-aw pipeline that runs green end to end**: actor gating, the
  Copilot agent, three-layer auth, GitHub App token minting, and safe-output PR
  plumbing — all at **zero LLM cost**.
- A **deterministic, dependency-light, tested bot** (no Rust builds, no second
  LLM, 59 tests) that produces correct YAML and idempotent shortcode injection
  (verified locally: 21 params including the test additions).
- A clear, documented understanding of gh-aw's **three identities** and the
  exact permissions each requires — the hardest and least-documented part.

## What's next

1. **Fix the no-op** (anchor the output path in the prompt / set
   `WEBSITE_ROOT`) so a real draft PR opens. This is the only thing between us
   and a fully demonstrated end-to-end run.
2. **Validate agent-written descriptions** land correctly on the new params.
3. **Run the auto-trigger chain** (merge a `krkn-hub` PR → PR on `website_2`)
   unattended, end to end.

---

## Request: a Red Hat API key + a "normal mode" engine

The Copilot Student engine got us to zero-cost runs, but it has real friction
for iterating:
- it is coupled to a personal Copilot subscription and a fine-grained PAT with a
  specific permission that is easy to mis-set (we lost time to exactly that);
- it is awkward for unattended/CI runs and for anyone else picking up the work.

**Ask:** a **Red Hat–provided LLM API key** (an OpenAI-compatible endpoint we can
point a "normal" gh-aw engine at). That lets us run the agent on a standard API
engine, test as often as we need, and hand the project off without each person
wiring up their own Copilot identity.

**Other options if a Red Hat key isn't available:**
- **GitHub Models PAT** (`Models: read`) — free tier, OpenAI-compatible; good for
  light testing but rate-limited and still a personal token.
- **OpenRouter with a small prepaid credit** — flexible model choice, but we
  already saw how fast an over-eager model can burn credit (problem #2); would
  need strict `max-turns`/token caps.
- **Stay on Copilot Student** — works and is free, but with the
  iteration/handoff friction above.

Recommended: **Red Hat key + normal engine** for development and CI, keep
**Copilot** configured as the zero-cost fallback (it is already wired and
commented in `doc-sync.md`).
