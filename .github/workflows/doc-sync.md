---
# Source workflow, compiled to doc-sync.lock.yml by `gh aw compile`.
# All deterministic work runs in the custom steps below, before the agent.
# The agent only commits the generated files and opens the pull request.

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

engine:
  id: copilot
  model: gpt-4o-mini

steps:
  - name: Checkout website
    uses: actions/checkout@v7
    with:
      persist-credentials: false
  - name: Resolve scenario
    id: scn
    env:
      DISPATCH_SCENARIO: ${{ github.event.inputs.scenario }}
      COMMENT_BODY: ${{ github.event.comment.body }}
    run: |
      if [ -n "$DISPATCH_SCENARIO" ]; then
        scenario="$DISPATCH_SCENARIO"
      else
        scenario="$(printf '%s' "$COMMENT_BODY" | awk 'NR==1{print $2}')"
      fi
      case "$scenario" in
        ''|*[!a-z0-9-]*)
          echo "invalid or missing scenario: '$scenario'" >&2
          exit 1 ;;
      esac
      echo "scenario=$scenario" >> "$GITHUB_OUTPUT"
  - name: Install docs bot
    run: pip3 install "git+https://github.com/StrikerEureka34/krkn-docs-bot-gh-aw.git@main"
  - name: Clone krkn-hub source
    run: git clone --depth 1 https://github.com/StrikerEureka34/krkn-hub.git "$RUNNER_TEMP/krkn-hub"
  - name: Generate parameter data and scaffold
    env:
      KRKN_HUB_PATH: ${{ runner.temp }}/krkn-hub
    run: python3 -m bot.doc_bot --scenario "${{ steps.scn.outputs.scenario }}" --scaffold

network:
  allowed:
    - defaults
    - github

tools:
  bash: ["git"]

max-turns: 3
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

Earlier workflow steps already regenerated this scenario's krkn-chaos parameter data files and injected the shortcode in the working tree. Your job is to commit them to a feature branch and open a pull request. Do not install anything or run the bot.

The scenario is `${{ github.event.inputs.scenario }}` and the triggering command was `${{ needs.pre_activation.outputs.matched_command }}`.

1. Create a feature branch and commit the generated files:
   - `git checkout -b docs-sync-${{ github.event.inputs.scenario }}`
   - `git add -A`
   - `git commit -m "docs-sync: ${{ github.event.inputs.scenario }} parameter tables"`
2. Call exactly one safe-output tool:
   - if the triggering command was `resync`, call `push_to_pull_request_branch` to update the scenario's existing pull request.
   - otherwise call `create_pull_request` with `branch` set to `docs-sync-${{ github.event.inputs.scenario }}`, a short title, and a body noting that the scenario's parameter data files and shortcode were regenerated from krkn-hub.

You must call exactly one safe-output tool before finishing. Never read or log secrets.
