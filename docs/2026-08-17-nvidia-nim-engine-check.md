# NVIDIA NIM as the bot's model

Written 2026-08-17. Can `integrate.api.nvidia.com` with
`nvidia/nemotron-3.5-lightning-30b-a3b` drive the bot, with the key held as a
repo secret?

Secret **names** only in this file. No values.

&ensp;

## Status, 2026-08-18: we reverted to Copilot

This document stands as the record of the investigation, and everything below
still holds. What changed the day after: we went back to
`engine: {id: copilot, model: gpt-4o-mini}` for normal testing. On that run all
six jobs went green **and the agent opened the PR itself**, which proves the two
workarounds below are optional on a supported vendor.

Nothing was deleted. The NVIDIA configuration sits commented in the fork's
`.github/workflows/doc-sync.md` under three blocks headed `NVIDIA PATH n of 3`,
so swapping back is uncommenting three blocks and recompiling.

| Fix from this investigation | Where it is now |
| --- | --- |
| The `openai/gpt-oss-20b` engine block | Commented, `NVIDIA PATH 1 of 3` |
| The NIM describer env | Commented, `NVIDIA PATH 2 of 3` |
| Writing the safe-output item and the patch ourselves | Commented, `NVIDIA PATH 3 of 3` |
| `_TIMEOUT` reading `LLM_TIMEOUT`, default 120s | Live in the fork's `describe.py`. Still upstream's only open describer gap |
| `threat-detection: false` | Removed, detection is on again |
| `tools: bash: ["*"]` | Removed. Opening a PR is a safe output and needs no tool |

The shipped `website-template/doc-sync.md` carries none of the NVIDIA path. It
ships Copilot, which is what the engine section of `fork-setup.md` recommends.

&ensp;

## Verdict: both halves work, proven in CI

Settled 2026-08-17 after eight runs. The bot runs end to end on an NVIDIA NIM
key with no Copilot inference anywhere.

| Use | Works? | Evidence |
| --- | --- | --- |
| Call 1, `describe.py` descriptions | **Yes** | Gap report: `NODE_READY_POLL_INTERVAL \| llm \| Controls how long to wait between Kubernetes API checks for the affected node` |
| Call 2, the engine, via `engine: copilot` BYOK | **Yes, with a caveat** | Runs, but never sends tool definitions, so it cannot call a safe-output tool. We write the item ourselves instead |
| Call 2, via `engine: codex` | **No** | Codex CLI dropped chat/completions in Feb 2026 |

**Three fixes were needed, and only the last two were bugs.**

| # | Fix | Why |
| --- | --- | --- |
| 1 | Model named `openai/gpt-oss-20b` | The api-proxy gates on the model name and permits only `copilot/*`, `anthropic/*`, `openai/*`, `google/*`, `gemini/*`. `20b` not `120b` because the larger model took 171s per call and hit `ECONNRESET` at 290s |
| 2 | Write the `create_pull_request` item ourselves, in `steps:` | Copilot CLI sends no tool definitions to a custom provider, so the agent cannot call the tool at any model or config. Must be `steps:` not `post-steps:`, which compile in after the ingest reads the file |
| 3 | `_TIMEOUT` configurable, default 120s | The old hardcoded 30s was shorter than the call. Same prompt measured 20.6s, 27.4s and 83.3s within one hour on the free tier |

Also write the patch ourselves with `git format-patch`. gh-aw needs **two**
inputs: the NDJSON item supplies the branch, title and body, and a separate
`/tmp/gh-aw/aw-*.patch` supplies the file changes. AWF only writes that patch
when the agent step succeeds, so without this a provider timeout still blocks
the PR even with a perfect item.

&ensp;

## The two model calls

Worth stating plainly, because the Slack thread on 2026-08-14 conflated them.

| | Where it runs | Job | Switch | Without it |
| --- | --- | --- | --- | --- |
| Call 1, the describer | `bot/describe.py`, inside a custom step | Writes descriptions no source has | `LLM_API_KEY` | Returns `{}`, cells stay empty, the gap report names each one. Run stays green |
| Call 2, the engine | The gh-aw agent, after every custom step | Opens or updates the PR | `engine:` | The run fails. Nothing else changes |

Verified in `describe.py`: no key means `_fail(...)` then `return {}` at line 163.
It posts to `<LLM_BASE_URL>/chat/completions` through stdlib `urllib`, with no
`openai` dependency.

Call 1 runs **before** the firewall is installed, so its host never needs a
`network.allowed` entry.

&ensp;

## Why not `codex`, which `fork-setup.md` recommended at the time

OpenAI removed `chat/completions` from the Codex CLI. Deprecation announced
2025-12-09, removed early February 2026. From 0.122 every custom provider must
set `wire_api = "responses"`.

gh-aw exposes no way to set `wire_api`. So `engine: codex` with
`OPENAI_BASE_URL` only works against an endpoint speaking the Responses API.

NIM does expose `/v1/responses`, so this is not impossible, but it rests on
gh-aw's bundled Codex defaulting to responses **and** NIM's implementation
matching. Two unknowns stacked, for no gain over the option below.

**`fork-setup.md` section 5b is stale independently of NVIDIA.** It tells the
reader to point `engine: codex` at an Ollama `/v1` base, and Ollama serves
chat/completions. That guidance would fail today.

&ensp;

## Why `copilot` BYOK is the right path

gh-aw treats three variables specially:

| Variable | Behaviour |
| --- | --- |
| `COPILOT_PROVIDER_BASE_URL` | Activates BYOK. When it is a literal URL, gh-aw **adds the hostname to the firewall allow-list automatically**, for the agent run and the threat-detection step |
| `COPILOT_PROVIDER_API_KEY` | Explicitly permitted to carry `${{ secrets.* }}` under strict mode, and **not leaked to the agent container** |
| `COPILOT_PROVIDER_BEARER_TOKEN` | Same treatment |

That answers the secrets question directly. Strict mode is mandatory on public
repos, and both `website_2` and `krkn-chaos/website` are public. The earlier
failure was strict mode rejecting a second `${{ secrets.* }}` in `engine.env`;
these three are the sanctioned exception.

It also removes the manual `network.allowed` entry, which is the constraint that
forced port 443 and killed the `llm.krkn-chaos.dev:11434` idea.

The fork already runs `engine: copilot`, so this is a field change rather than an
engine migration.

```yaml
engine:
  id: copilot
  model: nvidia/nemotron-3.5-lightning-30b-a3b
  env:
    COPILOT_PROVIDER_BASE_URL: https://integrate.api.nvidia.com/v1
    COPILOT_PROVIDER_API_KEY: ${{ secrets.LLM_API_KEY }}
```

`engine.model` rejects colons. This id has none.

&ensp;

## The model suits the job

The agent's whole job is one well-formed `create_pull_request` tool call.

| Fact | Source |
| --- | --- |
| Built for "frequent agent calls including tool use, output validation, result formatting and subagent delegation" | NVIDIA model card |
| RL-trained on multi-step tool use and structured output | Model card |
| Tool calling auto-enabled for Nemotron on NIM | NIM function-calling docs |
| 1M context | Model card |

That last row matters. `fork-setup.md:195` disables threat detection because it
is a roughly 68k-token scan and "a small local model will not handle it". 1M
context removes that argument, so threat detection could stay on.

&ensp;

## The larger consequence: this may retire the Mac mini

Almost all of `fork-setup.md` Step 4 exists to make a self-hosted model reachable
from a GitHub runner.

| Step 4 requirement | With NIM |
| --- | --- |
| OpenAI-compatible `/v1` | Native |
| A real certificate, since a runner has no `curl -k` | NVIDIA's public cert |
| Port 443 only, because `network.allowed` rejects a port | Standard 443, and BYOK auto-allowlists anyway |
| HTTPS, so the bearer key is not in cleartext | Yes |
| ngrok or certbot, plus an open port | None |
| No failover if the box is down | NVIDIA's problem |
| `threat-detection: false` | Can likely stay on |

It also clears a recorded blocker. `krkn-operator-expansion-plan.md` logs a
2026-08-13 probe finding the built-in endpoint
(`model.cclm-chaos.aws.rhperfscale.org`) **unreachable from GitHub Actions**:
`connect=0.000000s` and a 30 second timeout, port 443 filtered for GitHub's
egress ranges. NIM is a public endpoint with no such problem.

&ensp;

## Risks

| Risk | Why it matters | How it gets settled |
| --- | --- | --- |
| Copilot BYOK wire format | If BYOK speaks Responses rather than chat/completions, NIM has to serve `/v1/responses` well | The live run, then `gh aw logs` |
| Reasoning traces breaking the JSON parse | `describe.py` runs `_unfence` then parses JSON. A `<think>` block breaks it. The sample curl passes `enable_thinking: true` explicitly, implying default off, but that is inference | Read the gap report on the resulting PR |
| Rate limit | 40 requests per minute per model, account-wide | Test one scenario, not `globals` |
| Free credits | 1000 on signup, up to 5000 on request. NVIDIA staff have also said trial usage is rate-limited rather than credit-metered | Watch the first runs |
| "Not for production" | The free tier is positioned for prototyping | Fine for the demo, flag it at upstream handover |
| Threat detection doubles the spend | It reuses the engine | Off for the first test, then measure |

&ensp;

## Security review of the compiled lock

`gh aw compile` safe-update mode flagged one new restricted secret and asked for
review. Recorded here rather than in a PR body, because the PR this workflow
opens carries a fixed body written by the prompt.

**Change surface, from the compiled manifest:**

| | Before | After |
| --- | --- | --- |
| Secrets | `APP_PRIVATE_KEY`, `COPILOT_GITHUB_TOKEN`, `GH_AW_CI_TRIGGER_TOKEN`, `GH_AW_GITHUB_MCP_SERVER_TOKEN`, `GH_AW_GITHUB_TOKEN`, `GITHUB_TOKEN` | same, minus `COPILOT_GITHUB_TOKEN`, plus `LLM_API_KEY` |
| Actions | 10 | 9. **Zero added**, `actions/setup-node` dropped |
| Inference destination | GitHub Copilot | `integrate.api.nvidia.com` |

**`LLM_API_KEY`, reviewed and accepted for this test:**

| Check | Finding |
| --- | --- |
| Where it is used | Two functional sites only: `lock:573` the describer step, `lock:1029` the engine BYOK env |
| Does the agent see it | **No.** `lock:1022` passes `--exclude-env COPILOT_PROVIDER_API_KEY` to the firewall wrapper, so it is stripped from the agent container |
| Is it redacted from logs | **Yes.** Added to `GH_AW_SECRET_NAMES` at `lock:1087` |
| Blast radius if leaked | An NVIDIA free-tier inference key. No repo write, no GitHub scope |

**`COPILOT_GITHUB_TOKEN` disappearing is expected, not an accident.** BYOK routes
inference to the provider, so the Copilot credential path is not compiled in.
Only `GITHUB_COPILOT_INTEGRATION_ID` remains.

**Verified rather than trusted:** `integrate.api.nvidia.com` appears in the
firewall `allowDomains` list without anyone adding a `network.allowed` entry.
That confirms the auto-allowlist behaviour the docs claim.

**Flagged, not blocking:**

- The describer step runs before the firewall is installed, by design, so that
  call is not proxied or audited. The key still crosses HTTPS, and the content is
  public open-source parameter names.
- NVIDIA's retention policy for free-tier prompts is unread. Content sent is
  parameter names and existing public descriptions, so nothing private leaves.

&ensp;

## Result

| | |
| --- | --- |
| Date | 2026-08-16, run 31976564477 on `StrikerEureka34/website_2`, target `node-scenarios` |
| Jobs | `pre_activation` ✅ `activation` ✅ **`agent` ❌** `safe_outputs` ✅ `conclusion` ✅ |
| Engine | **Failed.** `400` with no body, 3 retries, exit 1 |
| Deterministic half | **Worked entirely.** Branch `docs-sync-164`, commit `40297a4`, 4 files changed, 376 insertions |
| Describer | **Unresolved.** The step passed, but whether NIM answered or it degraded to empty cells is not visible in the logs |

### What the failure was not

Ruled out from the artifacts, not guessed:

| Suspect | Evidence it is innocent |
| --- | --- |
| Auth | `isAuthError=false isAuthenticationFailedError=false`. The proxy also fetched NVIDIA's model catalog on the same key |
| The firewall | `integrate.api.nvidia.com` in `allowDomains`, and the catalog fetch succeeded. `target: integrate.api.nvidia.com` |
| Wire format | `url.path: /chat/completions`. **BYOK speaks chat/completions, not Responses.** The docs-level worry was wrong |
| The model id | The catalog holds 102 models, 25 of them Nemotron, and `nvidia/nemotron-3.5-lightning-30b-a3b` is present |
| A timeout | Each 400 came back in about 90ms |

### What it was: gh-aw's own api-proxy, not NVIDIA

**NVIDIA never saw the request.** The 400 came from the api-proxy sidecar that
gh-aw puts between the agent container and the provider.

Four hypotheses were tested and all died:

| Hypothesis | Test | Result |
| --- | --- | --- |
| Tool definitions rejected | curl with a `tools` array | 200, `finish_reason: tool_calls` |
| `stream_options` rejected | curl with `stream_options` added | 200 |
| Request too large | Probe from 500 to 46,347 chars of system prompt | 200 at every size |
| Something in the content | **Replay the captured 60,619-byte request verbatim** | **200** |

The last one is conclusive. The exact bytes Copilot CLI sent, replayed straight
at `integrate.api.nvidia.com`, succeed. So the rejection happened before the
request left the runner.

The reason is in the resolved firewall config:

```
enableApiProxy         True
enableTokenSteering    True
copilotProviderBaseUrl https://integrate.api.nvidia.com/v1
modelAliases.copilot   -> ['agent']
             agent     -> ['sonnet-6x','gpt-5.5','gpt-5.4','gpt-5.3','gemini-pro','any']
             any       -> ['copilot/*','anthropic/*','openai/*','google/*','gemini/*']
```

`nvidia/nemotron-3.5-lightning-30b-a3b` matches none of those globs. There is no
`nvidia/*` pattern, so token steering refuses the model and returns a bare 400.

Every symptom fits and none needed a special explanation:

| Symptom | Explanation |
| --- | --- |
| 400 in about 90ms | Rejected locally, no upstream round trip |
| No error body | The proxy's own bare 400, not a provider error |
| Model catalog fetched fine | `/models` is not model-gated |
| Identical bytes succeed by hand | Nothing between the caller and NVIDIA |

### Correction: the allowlist is one symptom, not the cause

An earlier version of this doc blamed the model allowlist. The allowlist is
real, but it is one visible effect of **api-proxy token steering**, which
resolves the provider after the workflow's explicit config and without checking
which provider slots are provisioned.

`github/gh-aw` issue #50113 covers it, open since 2026-08-03 and untouched since
2026-08-04. Its Case 2 is our engine and mode.

`sandbox.agent.token-steering: false` is the documented remedy and it exists
from **v0.84.4**. We run v0.80.9, so it does not compile for us.
`sandbox.agent.model-fallback: false` is documented on `main` but its changeset
is still unreleased in every version. Both were tried and rejected at compile
time. Naming an allowlisted model that the provider genuinely hosts is the
workaround that does not need an upgrade.

**Read the docs at the tag you run**, not at `main`. Two of the three knobs we
found on `main` do not exist in our release.

### The candidate fix

gh-aw separates the model name it gates on from the one it puts on the wire:

| Variable | Meaning, quoting the docs |
| --- | --- |
| `COPILOT_MODEL` | "Model to use; required by most providers". What gh-aw uses internally |
| `COPILOT_PROVIDER_MODEL_ID` | "Model ID sent on the wire when it differs from `COPILOT_MODEL`" |

So naming an allowlisted model for gh-aw while sending the real one to NVIDIA
should clear the gate. Untested:

```yaml
engine:
  id: copilot
  model: openai/gpt-4o                 # matches the openai/* pattern
  env:
    COPILOT_PROVIDER_BASE_URL: https://integrate.api.nvidia.com/v1
    COPILOT_PROVIDER_API_KEY: ${{ secrets.LLM_API_KEY }}
    COPILOT_PROVIDER_MODEL_ID: nvidia/nemotron-3.5-lightning-30b-a3b
```

**Whether this works turns on where the substitution happens.** If the proxy
swaps the id after checking the allowlist, it works. If Copilot CLI swaps it
before the proxy sees it, the proxy still sees `nvidia/...` and still refuses.
One run settles it.

Also learned along the way: `COPILOT_PROVIDER_WIRE_API` exists, so the wire
protocol is configurable for the copilot engine even though it is not for codex.

### The finding that matters more

**The run is direct evidence for Path 2.** Every deterministic step passed:
resolve, install, clone three sources, generate, scaffold, write the gap report,
branch and commit. The one thing that failed is the one thing Path 2 replaces
with `gh pr create`. The work was done and sitting on a branch; only the
PR-opening step could not complete.

### Where that leaves NVIDIA

Written mid-investigation. Both rows were resolved the same day, and the verdict
at the top of this file supersedes them:

| Use | Status then | Settled |
| --- | --- | --- |
| Engine, via `copilot` BYOK | Blocked on an opaque 400. The failure looks payload-shaped rather than model-shaped | Model-name gating in the api-proxy. Naming `openai/gpt-oss-20b` cleared it |
| Describer | The promising half, untested in isolation. `describe.py` sends a far simpler body with no tools | Works. It runs before the firewall and never carried the tools that broke the engine call |

&ensp;

## Sources

- [gh-aw engines](https://github.github.com/gh-aw/reference/engines/)
- [Codex chat/completions deprecation](https://github.com/openai/codex/discussions/7782)
- [NIM function calling](https://docs.nvidia.com/nim/large-language-models/latest/function-calling.html)
- [NIM API reference](https://docs.nvidia.com/nim/large-language-models/latest/reference/api-reference.html)
- [Model card](https://build.nvidia.com/nvidia/nemotron-3.5-lightning-30b-a3b/modelcard)
- [Nemotron 3.5 Lightning announcement](https://developer.nvidia.com/blog/nvidia-nemotron-3-5-lightning-delivers-fast-accurate-specialized-task-execution-for-long-running-agents/)
- [NIM free tier and limits](https://decodethefuture.org/en/nvidia-nim-api-pricing-limits-guide/)
