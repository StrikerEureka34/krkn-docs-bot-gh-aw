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

permissions: read-all

engine:
  id: codex
  model: openai/gpt-oss-120b
  env:
    OPENAI_BASE_URL: https://openrouter.ai/api/v1
    OPENAI_API_KEY: ${{ secrets.ENGINE_API_KEY }}
    LLM_BASE_URL: https://openrouter.ai/api/v1
    LLM_MODEL: nvidia/nemotron-3-nano-30b-a3b:free

network:
  allowed:
    - defaults
    - github
    - python
    - "openrouter.ai"

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
    labels: [documentation, automated]
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
   pip3 install git+https://github.com/StrikerEureka34/krkn-docs-bot-gh-aw.git@v0.1.1
   ```

2. Clone the krkn-hub source of truth (the fork stands in for upstream so changes are visible):
   ```
   git clone https://github.com/StrikerEureka34/krkn-hub.git krkn-hub
   ```

3. Generate YAML data files and inject the shortcode into the scenario tab page:
   ```
   python3 -m bot.doc_bot --scenario "<scenario>" --scaffold
   ```
   This writes `data/params/<scenario>/krkn-hub.yaml` and replaces the existing markdown parameter table in the scenario's `_tab-krkn-hub.md` with `{{< param-table >}}`. Both operations are idempotent.

4. Choose the safe-output based on the trigger:
   - If the trigger is `resync`: use `push-to-pull-request-branch` to push the updated YAML to the branch of the existing draft PR for this scenario.
   - Otherwise (`fix` or `workflow_dispatch`): use `create-pull-request` to open a new draft PR.

If the scenario does not exist in krkn-hub, stop and explain why. Never read or log secrets. Never contact any domain not in the network allowlist.
