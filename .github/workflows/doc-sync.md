---
# Source workflow, compiled to doc-sync.lock.yml by `gh aw compile`.
# All deterministic work runs in the custom steps below, before the agent.
# The agent only commits the generated files and opens the pull request.

on:
  slash_command:
    name: [fix, resync]
  workflow_dispatch:
    inputs:
      scenarios:
        description: "Scenario name(s), space-separated (e.g. 'node-scenarios pod-scenarios')"
        required: false
  # TESTING: allow anyone to run /fix and /resync. Tighten to
  # [admin, maintainer, write] for production. The comment must still start
  # with "/fix <scenario>" or "/resync" as its first text.
  roles: all
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
  - name: Resolve scenarios
    id: scn
    env:
      DISPATCH_SCENARIOS: ${{ github.event.inputs.scenarios }}
      COMMENT_BODY: ${{ github.event.comment.body }}
      PR_NUMBER: ${{ github.event.issue.number }}
      REPO: ${{ github.repository }}
      GH_TOKEN: ${{ github.token }}
    run: |
      # A merged krkn-hub PR can touch several scenarios (space-separated dispatch
      # input); a /fix comment names exactly one; /resync derives them from the PR.
      if [ -n "$DISPATCH_SCENARIOS" ]; then
        scenarios="$DISPATCH_SCENARIOS"
      else
        scenarios="$(printf '%s' "$COMMENT_BODY" | awk 'NR==1{$1="";print}')"
        if [ -z "$scenarios" ] && [ -n "$PR_NUMBER" ]; then
          scenarios="$(gh api "repos/$REPO/pulls/$PR_NUMBER/files" --jq '.[].filename' 2>/dev/null \
            | grep -oE 'data/params/[a-z0-9-]+/' | cut -d/ -f3 | sort -u | tr '\n' ' ')"
        fi
      fi
      scenarios="$(echo $scenarios | tr -s ' ')"
      if [ -z "$scenarios" ]; then
        echo "no scenario given" >&2
        exit 1
      fi
      # Targets are scenario ids plus the literal "globals". Both fit a-z0-9-,
      # so this guard stays exactly as strict as before.
      for s in $scenarios; do
        case "$s" in
          *[!a-z0-9-]*)
            echo "invalid target: '$s'" >&2
            exit 1 ;;
        esac
      done
      echo "scenarios=$scenarios" >> "$GITHUB_OUTPUT"
  - name: Install docs bot
    run: pip3 install "git+https://github.com/StrikerEureka34/krkn-docs-bot-gh-aw.git@main"
  - name: Clone krkn-hub source
    run: git clone --depth 1 https://github.com/StrikerEureka34/krkn-hub.git "$RUNNER_TEMP/krkn-hub"
  - name: Clone krkn source
    # Global krknctl params live here. The bot refuses to run without it rather
    # than silently emitting a degraded skip list.
    run: git clone --depth 1 https://github.com/StrikerEureka34/krkn.git "$RUNNER_TEMP/krkn"
  - name: Generate parameter data and scaffold
    env:
      KRKN_HUB_PATH: ${{ runner.temp }}/krkn-hub
      KRKN_PATH: ${{ runner.temp }}/krkn
    run: |
      for target in ${{ steps.scn.outputs.scenarios }}; do
        echo "Generating: $target"
        case "$target" in
          globals)
            # One file per source under data/params/globals/, then replace the
            # tables on the two global pages with group-filtered shortcode calls.
            python3 -m bot.globals --krkn-hub "$KRKN_HUB_PATH" --krkn "$KRKN_PATH" --scaffold ;;
          *)
            python3 -m bot.doc_bot --scenario "$target" --scaffold ;;
        esac
      done
  - name: Commit generated files to a branch
    env:
      TARGETS: ${{ steps.scn.outputs.scenarios }}
    run: |
      git config user.name "krkn-docs-bot"
      git config user.email "krkn-docs-bot@users.noreply.github.com"
      git checkout -b "docs-sync-${{ github.run_number }}"
      git add -A

      # Everything a reviewer needs goes in the commit message, which is written
      # here and never passes through the agent. The PR body stays short enough
      # that a small model cannot mangle it.
      changed="$(git diff --cached --name-status)"
      added="$(printf '%s\n' "$changed" | grep -c '^A' || true)"
      modified="$(printf '%s\n' "$changed" | grep -c '^M' || true)"
      deleted="$(printf '%s\n' "$changed" | grep -c '^D' || true)"
      summary="$added added, $modified modified, $deleted removed"

      git commit -s -F - <<COMMIT_MSG || echo "no changes to commit"
      docs-sync: parameter tables for $TARGETS

      $summary.

      Generated from:
      - krkn-hub/env.sh and each scenario's krknctl-input.json
      - krkn/containers/krknctl-input.json for the global parameters

      These files are derived. Edit the source, not the table.

      $changed
      COMMIT_MSG

network:
  allowed:
    - defaults
    - github

max-turns: 3
timeout-minutes: 15

safe-outputs:
  github-app:
    app-id: ${{ vars.APP_ID }}
    private-key: ${{ secrets.APP_PRIVATE_KEY }}
  create-pull-request:
    # Threat detection (a separate ~68k-token LLM scan) runs by default and is
    # kept ON for the mentor demo. To disable it for this workflow, add:
    #   threat-detection: false
    target-repo: "StrikerEureka34/website_2"
    draft: true
    title-prefix: "[docs-sync] "
    max: 1
  push-to-pull-request-branch:
    target-repo: "StrikerEureka34/website_2"
---

# Doc Sync

Earlier workflow steps already regenerated the changed krkn-chaos scenarios' parameter data files, injected the shortcode, and committed everything to the branch `docs-sync-${{ github.run_number }}`. Your only job is to open a single pull request for that branch. Do not run git or any other command.

The triggering command was `${{ needs.pre_activation.outputs.matched_command }}`.

Call exactly one safe-output tool:
- if the triggering command was `resync`, call `push_to_pull_request_branch` to update the existing pull request.
- otherwise call `create_pull_request` with `branch` set to `docs-sync-${{ github.run_number }}`.

Set `title` to exactly `Regenerate parameter tables` and `body` to exactly the three
lines below. Copy them character for character. Do not summarise them, do not add a
file list, do not add counts, do not add anything else.

```
Parameter tables regenerated from source. The commit message lists the targets, the file counts and the source files.

These files are generated. Edit the source, not the table.
```

Every fact about this run already lives in the commit message, which was written
deterministically and is visible in the diff. You do not need to restate it.

You must call exactly one safe-output tool before finishing. Never read or log secrets.
