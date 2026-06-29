---
# .github/workflows/doc-sync.md
# Source workflow, lives in krkn-docs-bot-gh-aw.
# Compiled to doc-sync.lock.yml by `gh aw compile` and deployed to the website fork.

on:
  slash_command:
    - fix
    - resync
  workflow_dispatch:
    inputs:
      scenario:
        description: "Scenario name (e.g. node-scenarios)"
        required: true

permissions: read-all

roles: [admin, maintainer, write]

engine:
  id: codex
  model: openai/gpt-oss-120b
  env:
    OPENAI_BASE_URL: https://openrouter.ai/api/v1
    OPENAI_API_KEY: ${{ secrets.ENGINE_API_KEY }}
    LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
    LLM_BASE_URL: https://openrouter.ai/api/v1
    LLM_MODEL: nvidia/nemotron-3-nano-30b-a3b:free

network:
  allowed:
    - defaults
    - "openrouter.ai"
    - "github.com"
    - "objects.githubusercontent.com"
    - "pypi.org"
    - "files.pythonhosted.org"

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

**Scenario:** ${{ inputs.scenario || github.event.slash_command.args }}
**Trigger:** ${{ github.event.slash_command.name || 'workflow_dispatch' }}

Follow these steps exactly. Do not invent parameters or change any value already present in an existing YAML file.

1. Install the docs bot:
   ```
   pip3 install git+https://github.com/StrikerEureka34/krkn-docs-bot-gh-aw.git@v0.1.0
   ```

2. Clone the krkn-hub source of truth:
   ```
   git clone https://github.com/krkn-chaos/krkn-hub.git krkn-hub
   ```

3. Generate YAML data files for the scenario (data only, do NOT pass --scaffold):
   ```
   python3 -m bot.doc_bot --scenario "<scenario>"
   ```
   This writes to `data/params/<scenario>/`. It is idempotent: re-running never overwrites existing descriptions.

4. Choose the safe-output based on the trigger:
   - If the trigger is `resync`: use `push-to-pull-request-branch` to push the updated YAML to the branch of the existing draft PR for this scenario.
   - Otherwise (`fix` or `workflow_dispatch`): use `create-pull-request` to open a new draft PR.

If the scenario does not exist in krkn-hub, stop and explain why. Never read or log secrets. Never contact any domain not in the network allowlist.
