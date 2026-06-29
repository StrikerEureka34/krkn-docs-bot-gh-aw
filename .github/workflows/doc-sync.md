---
# .github/workflows/doc-sync.md
# Source workflow, lives in krkn-docs-bot-gh-aw.
# Compiled to doc-sync.lock.yml by `gh aw compile` and deployed to the website fork.

on:
  slash_command:
    name: [fix, resync]
  workflow_dispatch:
    inputs:
      scenario:
        description: "Scenario name (e.g. node-scenarios)"
        required: false
  roles: [admin, maintainer, write]
  bots: [krkn-docs-bot]

permissions: read-all

# Engine options (exactly one active block below):
#
# (a) Copilot (ACTIVE): zero cost on the Student plan via COPILOT_GITHUB_TOKEN.
#     Lower-tier model (gpt-4o-mini) to ease the utility-model rate limit.
engine:
  id: copilot
  model: gpt-4o-mini
#
# (b) OpenAI direct: ENGINE_API_KEY secret holds an sk-... OpenAI key.
# engine:
#   id: codex
#   model: gpt-4o
#   env:
#     OPENAI_API_KEY: ${{ secrets.ENGINE_API_KEY }}
#
# (c) Gemini: needs GEMINI_API_KEY secret. Note: the safeoutputs MCP tools did
#     not register under the Gemini CLI in gh-aw v0.80.9, so it could not open PRs.
# engine:
#   id: gemini
#   model: gemini-2.5-flash
#
# (d) OpenRouter free router: ENGINE_API_KEY holds an OpenRouter key. The free
#     providers rejected the Codex tool-call format (namespace vs function), so
#     it could not open PRs.
# engine:
#   id: codex
#   model: openrouter/free
#   env:
#     OPENAI_BASE_URL: https://openrouter.ai/api/v1
#     OPENAI_API_KEY: ${{ secrets.ENGINE_API_KEY }}

network:
  allowed:
    - defaults
    - github
    - python
    # - "openrouter.ai"                        # used with OpenRouter engine
    # - "api.openai.com"                       # used with OpenAI direct engine
    # - "generativelanguage.googleapis.com"    # used with Gemini engine

tools:
  bash: ["python3", "pip3", "git"]

max-ai-credits: 50
max-daily-ai-credits: 1000
max-turns: 10
timeout-minutes: 15

safe-outputs:
  github-app:
    app-id: ${{ vars.APP_ID }}
    private-key: ${{ secrets.APP_PRIVATE_KEY }}
  create-pull-request:
    target-repo: "StrikerEureka34/website_2"
    draft: true
    title-prefix: "[docs-sync] "
    max: 1
  push-to-pull-request-branch:
    target-repo: "StrikerEureka34/website_2"
---

# Doc Sync

You are a documentation sync assistant for krkn-chaos scenarios.

Determine the target scenario from whichever trigger fired:
- For a manual run, it is the `scenario` input: `${{ github.event.inputs.scenario }}`.
- For a slash command, it is the word after the command in the triggering comment, for example `/fix node-scenarios` means the scenario is `node-scenarios`.

Follow these steps exactly. Do not invent parameters or change any value already present in an existing YAML file.

1. Install the docs bot:
   ```
   pip3 install git+https://github.com/StrikerEureka34/krkn-docs-bot-gh-aw.git@v0.1.6
   ```

2. Clone the krkn-hub source of truth (the fork stands in for upstream so changes are visible):
   ```
   git clone https://github.com/StrikerEureka34/krkn-hub.git krkn-hub
   ```

3. From the repository root (the website checkout you are already in, NOT inside the `krkn-hub/` clone), generate the YAML data files and inject the shortcode into the scenario tab page:
   ```
   python3 -m bot.doc_bot --scenario "<scenario>" --scaffold
   ```
   The bot writes its output relative to the current directory, so the data file lands at `./data/params/<scenario>/krkn-hub.yaml` in the **repository root** — it does NOT go inside the cloned `krkn-hub/` directory (that holds only the source `env.sh`). It also replaces the existing markdown parameter table in the scenario's `_tab-krkn-hub.md` with `{{< param-table >}}`. Both operations are idempotent. The bot preserves descriptions that already exist and writes a generic placeholder (`Configures <param>.`) only for newly added or changed parameters.

4. Confirm the data file was written, then improve only the placeholder descriptions. List `./data/params/<scenario>/` (at the repository root, not under `krkn-hub/`) to find the generated `*.yaml`. In each, find the `description` fields that read as a generic placeholder (`Configures ...`) and replace each with one clear, accurate sentence describing what that parameter does, based on its name and default. These are the new or changed parameters. Do not change any `name`, `type`, or `default`, and do not touch any description that is not a placeholder. If no data file was generated, the scenario has no new parameters — only then is `noop` appropriate.

5. Choose the safe-output based on the trigger:
   - If the trigger is `resync`: use `push-to-pull-request-branch` to push the updated YAML to the branch of the existing draft PR for this scenario.
   - Otherwise (`fix` or `workflow_dispatch`): use `create-pull-request` to open a new draft PR.

If the scenario does not exist in krkn-hub, stop and explain why. Never read or log secrets. Never contact any domain not in the network allowlist.
