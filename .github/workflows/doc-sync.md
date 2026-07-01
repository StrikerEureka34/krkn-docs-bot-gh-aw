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
#     gpt-4o: mini confabulated false failures and no-op'd even with files present.
#     With agent editing removed, gpt-4o makes ~5 light calls (no patch retries),
#     so it stays under the utility-model rate limit and reads ls correctly.
engine:
  id: copilot
  model: gpt-4o
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
  # The agent uses bash + safe-outputs only. Keep the github MCP at the minimum
  # single toolset (empty is rejected) to cut per-turn tool-schema tokens.
  github:
    toolsets: [context]
  bash: ["python3", "pip3", "git"]

max-ai-credits: 50
max-daily-ai-credits: 1000
max-turns: 6
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

1. Install the docs bot into a fixed folder outside the repo (so it never leaks into the PR, and so the module is found regardless of the runner's Python or user-site config):
   ```
   pip3 install --target /tmp/gh-aw/botpkg git+https://github.com/StrikerEureka34/krkn-docs-bot-gh-aw.git@v0.1.6
   ```

2. Clone the krkn-hub source of truth (the fork stands in for upstream so changes are visible):
   ```
   git clone https://github.com/StrikerEureka34/krkn-hub.git krkn-hub
   ```

3. From the repository root (the website checkout you are already in, NOT inside the `krkn-hub/` clone), generate the YAML data files and inject the shortcode into the scenario tab page. Point `PYTHONPATH` at the install folder from step 1 so the module resolves on the first try:
   ```
   PYTHONPATH=/tmp/gh-aw/botpkg python3 -m bot.doc_bot --scenario "<scenario>" --scaffold
   ```
   The bot writes its output relative to the current directory, so the data file lands at `./data/params/<scenario>/krkn-hub.yaml` in the **repository root** — it does NOT go inside the cloned `krkn-hub/` directory (that holds only the source `env.sh`). It also replaces the existing markdown parameter table in the scenario's `_tab-krkn-hub.md` with `{{< param-table >}}`. Both operations are idempotent. The bot preserves descriptions that already exist and writes a generic placeholder (`Configures <param>.`) only for newly added or changed parameters.

4. List `./data/params/<scenario>/` (at the repository root, not under `krkn-hub/`). Decide strictly from what it lists:
   - If it lists one or more `*.yaml` files, the sync succeeded: you MUST continue to step 5 and create the pull request. Do NOT call `noop`, and do NOT claim the scenario is missing when YAML files are present.
   - Only if the directory is empty or does not exist may you call `noop`.
   Do not edit the generated YAML files. The bot has already filled every `description` with a sensible default, so leave the files exactly as generated and go straight to creating the pull request.

5. Choose the safe-output based on the trigger:
   - If the trigger is `resync`: use `push-to-pull-request-branch` to push the updated YAML to the branch of the existing draft PR for this scenario.
   - Otherwise (`fix` or `workflow_dispatch`): use `create-pull-request` to open a new draft PR.

Never read or log secrets. Never contact any domain not in the network allowlist.
