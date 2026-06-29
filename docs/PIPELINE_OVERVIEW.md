# Pipeline Overview — Bird's-Eye View

A map of the whole system: the repos, the data flow, what every job in the
runner does, and the features the bot ships. Pair with `JOURNAL.md` (the story
and the problems); this file is the reference.

---

## 1. The three repos at a glance

```
 krkn-hub (fork)                website_2 (fork of website)        krkn-docs-bot-gh-aw
 ───────────────                ───────────────────────────        ───────────────────
 scenario env.sh   ── merge ──▶ trigger-docs-sync.yml              bot/ (Python package)
 (source of truth)              doc-sync.lock.yml  ◀── deploy ───── .github/workflows/
 trigger-docs-sync.yml          doc-sync.md        ◀── deploy ─────   doc-sync.md (source)
                                draft PR lands here                 released as pip tags
```

- **krkn-hub** — where parameters live and where a merge starts everything.
- **website_2** — where the workflow runs and where the draft PR is opened.
- **krkn-docs-bot-gh-aw** — where the bot and the workflow *source* are authored
  and versioned. The compiled lock + prompt are copied into `website_2`.

> Key fact: the compiled `doc-sync.lock.yml` does a **runtime import** of
> `doc-sync.md` (`{{#runtime-import .github/workflows/doc-sync.md}}`). The prompt
> body — including the pinned `pip install ...@vX.Y.Z` line — lives in the `.md`,
> so **both files must be deployed together** to `website_2`.

---

## 2. End-to-end data flow

```
[1] Merge PR into krkn-hub (fork main)
        │  push event
        ▼
[2] trigger-docs-sync.yml (on krkn-hub)
        │  mint GitHub App token → repository_dispatch
        ▼
[3] doc-sync.lock.yml activates (on website_2)        ← the gh-aw workflow
        │
        ▼
[4] Copilot agent runs:
        pip install krkn-docs-bot-gh-aw@vX.Y.Z
        git clone krkn-hub
        python3 -m bot.doc_bot --scenario <s> --scaffold
          → writes ./data/params/<s>/krkn-hub.yaml   (deterministic)
          → injects {{< param-table >}} into _tab-krkn-hub.md (idempotent)
        agent rewrites placeholder descriptions for new/changed params
        declares safe-output: create-pull-request
        │
        ▼
[5] safe_outputs job: mint App token → open DRAFT PR on website_2
```

A `resync` trigger uses `push-to-pull-request-branch` instead of
`create-pull-request`, to update an existing draft PR's branch.

---

## 3. What each runner job does (gh-aw compiled jobs)

When `doc-sync.lock.yml` runs, gh-aw splits it into a fixed set of jobs. This is
the order you see in the Actions UI:

| Job | Purpose | What "green" means |
|-----|---------|--------------------|
| **pre_activation** | Gate: is this actor/trigger allowed? Checks `roles:` (humans) and `on.bots:` (App actors). | The trigger is authorized; the run may proceed. |
| **activation** | Set up the agent: prepare the prompt (system blocks + runtime-imported `doc-sync.md`), MCP tool servers, firewall config. | Prompt assembled, tools registered. |
| **agent** | The actual Copilot run: installs the bot, clones the hub, runs the scaffold, improves descriptions, and **declares** safe-outputs (it does not perform writes directly). | The agent finished and emitted a structured intent (a PR, or a `noop`). |
| **detection** | Threat / prompt-injection (XPIA) scan over the agent's output before any write happens. | No malicious or out-of-policy output detected. |
| **safe_outputs** | **Performs** the declared safe-outputs: mints the GitHub App token and opens/updates the draft PR on `website_2`. | The PR was created (or skipped, if the agent emitted `noop`). |
| **conclusion** | Final status: reaction comments, and on failure it opens an `[aw] ... reported incomplete` issue. | Run concluded; status reported. |

> Separation of concerns to note for mentors: the **agent only declares intent**
> (an LLM is never handed write credentials). A separate **safe_outputs** job,
> running with the minted App token, performs the actual write. `detection` sits
> between them. This is gh-aw's security model and it is the reason there are so
> many auth layers.

---

## 4. The three identities (who authenticates what)

| Layer | Credential | Type | Scope it needs |
|-------|-----------|------|----------------|
| Agent reasoning (the LLM engine) | `COPILOT_GITHUB_TOKEN` | fine-grained PAT | `Copilot Requests: Read-only` |
| File ops in the agent sandbox | `GITHUB_TOKEN` | auto-injected | repo contents (default) |
| Writing the PR to website_2 | App token from `vars.APP_ID` + `secrets.APP_PRIVATE_KEY` | GitHub App | Contents w, Pull requests w, **Issues w**, **Administration r**, Actions |

The App's Issues + Administration grants are non-obvious but required:
`create-pull-request` always requests `issues: write`, and a cross-repo target
adds `administration: read`. (See `JOURNAL.md` problem #6.)

---

## 5. Features the bot ships

| Feature | Where | Notes |
|---------|-------|-------|
| Parse scenario parameters | `bot/parser.py` | reads `env.sh` and `krknctl-input.json`; respects a skip-list of globally-documented common vars (`all-scenario-env.md`) |
| Emit structured data file | `bot/emitter.py` | `data/params/<scenario>/<source>.yaml`, byte-stable output |
| Description resolution | `bot/descriptions.py` | priority: existing file desc → source desc → deterministic placeholder (`Configures <param>.`); the **agent** upgrades placeholders for new params |
| Shortcode injection | `bot/scaffold.py` | replaces the Markdown parameter table with `{{< param-table >}}`; handles **bare** (no leading pipe) tables; **idempotent** |
| Drift scan (standalone) | `bot/drift_scanner.py`, `bot/github_client.py` | not used in the gh-aw path; for standalone runs |
| Deterministic, no runtime LLM | `bot/doc_bot.py` | no `openai`, no Rust deps; the agent owns prose |

---

## 6. Current status & the one open item

- **Green:** gating, agent, all three auth layers, App-token mint, safe-outputs.
- **Open:** the agent globs for the YAML inside `krkn-hub/data/params/...` but
  the bot writes it to the **workspace root** (`./data/params/...`). Result: a
  `noop` instead of a PR. Fix = anchor the output path in the prompt (or set
  `WEBSITE_ROOT`). One line. See `JOURNAL.md` problem #10.

---

## 7. Versions

`v0.1.0` → `v0.1.6`. The workflow installs a **pinned tag**; bumping the bot
means tagging a release and updating the `pip install ...@vX.Y.Z` line in
`doc-sync.md`, then re-deploying both workflow files to `website_2`.
