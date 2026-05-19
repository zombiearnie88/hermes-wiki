# Hermes Wiki Telegram Q&A And Admin Deployment Plan

## Goal

Ship the first deployable Hermes-wiki product shape for small clinics, hospital departments, academic groups, and research teams:

- Telegram-first Q&A for normal members
- Admin-only wiki operations for ingest, status, config, and rebuild workflows
- BYOK for organizations with their own LLM budget
- Managed credits for smaller teams that want a low-friction pilot
- Hermes Agent remains the runtime owner for wiki generation and Q&A

This plan treats Hermes-wiki as a Hermes Agent plugin, not as a standalone chatbot platform.

## Product Boundary

Hermes-wiki should be positioned as a private knowledge retrieval assistant for internal documents.

It should not be positioned as a clinical decision system, diagnostic agent, or autonomous treatment recommender.

Every medical deployment should include these default rules:

- answer only from indexed wiki content
- cite source pages for all substantive claims
- say when the answer is not present in the wiki
- include a concise medical safety disclaimer
- preserve audit logs for admin review

## Target User Segments

### BYOK Segment

Best fit:

- hospitals
- large clinics
- research institutes
- universities
- well-funded departments

Why BYOK fits:

- they already have budget and procurement channels for AI services
- they may need direct control over provider choice, billing, and data-processing terms
- they may prefer OpenAI, Anthropic, Gemini, Azure OpenAI, AWS Bedrock, or a private endpoint

### Managed Credits Segment

Best fit:

- small private clinics
- small academic groups
- internal hospital departments running a pilot
- teams that want to try AI without opening a separate LLM provider account

Why managed credits fit:

- onboarding is faster
- pricing can be low and predictable
- the customer does not manage API keys
- it creates an upgrade path into BYOK or on-prem deployments

## Core Architecture

```text
Telegram user
-> Hermes Gateway
-> Hermes session
-> hermes-wiki plugin command/tool/router
-> role policy
-> wiki Q&A or admin operation
-> WikiLLMClient
-> Hermes AIAgent or managed external gateway
-> LLM provider
```

The key design rule is that Q&A, ingest generation, rebuild generation, and future summarization jobs should not call `AIAgent` directly from scattered code paths.

They should go through a single plugin-owned interface:

```python
WikiLLMClient.generate(
    workspace_id=workspace_id,
    user_id=user_id,
    task="wiki_qa",
    messages=messages,
    model=model,
)
```

`WikiLLMClient` decides:

- whether the workspace uses BYOK, managed internal credits, or managed external credits
- whether quota is available
- which model/provider are allowed
- how usage should be logged
- whether to call Hermes `AIAgent` locally or a remote managed credits service

## Permission Model

Use two separate authorization layers.

### Layer 1: Hermes Gateway Access

This controls who can talk to the Telegram bot at all.

```env
TELEGRAM_ALLOWED_USERS=111111,222222,333333
```

or Hermes Gateway DM pairing.

This layer should remain owned by Hermes Gateway.

### Layer 2: Hermes Wiki Roles

This controls what an authorized Telegram user can do inside Hermes-wiki.

Add a plugin-level policy file or config section:

```yaml
access:
  admins:
    - "111111"
  qa_users:
    - "111111"
    - "222222"
    - "333333"
```

Environment override for simple deployments:

```env
HERMES_WIKI_ADMIN_USERS=111111
HERMES_WIKI_QA_USERS=111111,222222,333333
```

Role behavior:

| Operation | QA User | Admin |
|---|---:|---:|
| Ask wiki questions | Yes | Yes |
| Read cited sources | Yes | Yes |
| List source documents | Optional | Yes |
| Add documents | No | Yes |
| Rebuild wiki/index | No | Yes |
| Change provider/model config | No | Yes |
| View usage/quota | No | Yes |
| View audit logs | No | Yes |

Permission checks must happen before any LLM call. Do not rely on prompt instructions to block admin actions.

## Telegram Command Surface

### Normal Members

Allowed commands:

```text
/ask <question>
/wiki-help
/wiki-sources <last-answer-source-id>
```

Plain natural-language messages in DM can be treated as Q&A.

Normal members must not be able to call plugin write operations through prompt injection.

### Admins

Allowed commands:

```text
/wiki-add <path-or-upload-id>
/wiki-status
/wiki-list
/wiki-config ...
/wiki-rebuild
/wiki-usage
/wiki-quota
/wiki-audit
```

The current plugin already has `init`, `add`, `status`, `list`, `config`, and `deps` surfaces. The MVP should extend these with explicit role checks and Q&A-specific read-only surfaces.

## Q&A MVP Behavior

The Q&A workflow should be read-only.

```text
Telegram message
-> role check
-> workspace resolution
-> retrieve candidate wiki pages
-> construct grounded prompt
-> WikiLLMClient.generate(task="wiki_qa")
-> validate citations
-> return answer
-> append audit event
```

MVP retrieval can start simple:

- read `wiki/index.md`
- search `wiki/summaries/`
- search `wiki/concepts/`
- include relevant `wiki/sources/` snippets when available
- prefer deterministic keyword/BM25-style retrieval before vector search

Q&A prompt constraints:

- use only provided wiki context
- cite every factual claim using source labels
- if the wiki context does not answer the question, say so
- do not invent drug doses, contraindications, or treatment steps
- include document date/version if present in frontmatter

Example response shape:

```text
Answer:
The internal guideline says ... [1]

Sources:
[1] wiki/sources/meningitis-protocol.md
[2] wiki/concepts/ceftriaxone.md

Safety note: This answer only summarizes indexed internal documents and does not replace clinical judgment.
```

## Admin MVP Behavior

Admin commands should keep using the existing command implementation where possible.

Recommended implementation pattern:

```text
Telegram command
-> Hermes Gateway authorization
-> hermes-wiki role check
-> existing command/tool function
-> audit event
-> Telegram response
```

Do not duplicate ingest logic for Telegram. Keep `commands.py` or the plugin tool layer as the source of truth.

### Rebuild Operation

`/wiki-rebuild` should be added after the Q&A MVP only if there is a clear rebuild target.

Minimum behavior:

- rebuild `wiki/index.md` from current summaries and concepts
- optionally regenerate summaries/concepts when explicitly requested
- preserve `raw/`, `wiki/sources/`, and `.hermeskb/hashes.json`
- append an audit event

Suggested command split:

```text
/wiki-rebuild-index
/wiki-rebuild-all --confirm
```

This avoids accidental expensive regeneration.

## Provider Modes

Hermes-wiki should support three provider modes in config.

```yaml
llm:
  mode: byok
  provider: openai
  model: gpt-4.1-mini
```

```yaml
llm:
  mode: managed
  managed_endpoint: https://llm-gateway.example.com
  workspace_token_ref: HERMES_WIKI_MANAGED_TOKEN
  model: clinic-mini-default
```

```yaml
llm:
  mode: local
  provider: openai-compatible
  base_url: http://localhost:11434/v1
  model: local-model-name
```

For MVP, keep one active provider mode per workspace.

## BYOK Implementation Plan

BYOK means the customer owns the LLM provider account and pays the provider directly.

Implementation requirements:

- store provider and model in `.hermeskb/config.yaml`
- store secrets outside normal wiki content
- allow secret values from environment variables
- never echo full API keys in Telegram responses
- add a connection test command for admins
- log usage metadata, but do not enforce managed-credit deductions

Suggested commands:

```text
/wiki-provider status
/wiki-provider set byok --provider openai --model gpt-4.1-mini
/wiki-provider test
```

Secret storage policy:

- local self-hosted deployments can use `~/.hermes/.env`
- Docker deployments should use Docker secrets or environment variables
- future web admin should encrypt secrets at rest

## Managed Credits Implementation Plan

Managed credits means the customer buys Hermes-wiki usage quota and does not manage provider API keys.

### Hosted Managed Credits

Use this when the service operator hosts Hermes and Hermes-wiki for the customer.

```text
Customer Telegram
-> operator-hosted Hermes Gateway
-> operator-hosted Hermes-wiki plugin
-> internal WikiLLMClient quota check
-> Hermes AIAgent using operator API key
-> provider
```

This is simplest for early pilots because the provider key stays on the operator-controlled server.

### Self-Hosted Managed Credits

Use this when the customer runs Hermes-wiki on their own server but wants to consume operator-managed credits.

```text
Customer Telegram
-> customer Hermes Gateway
-> customer Hermes-wiki plugin
-> operator managed LLM gateway API
-> provider using operator API key
```

The plugin must not ship with the operator's real provider key.

The customer installation stores only a workspace/license token:

```env
HERMES_WIKI_MANAGED_TOKEN=hwk_live_xxx
```

The external managed gateway verifies that token and enforces quota.

## Managed Credits Data Model

Start with a minimal file-backed or SQLite-backed ledger.

Workspace config:

```yaml
managed_credits:
  plan: clinic_mini
  monthly_token_limit: 2000000
  monthly_question_limit: 500
  used_tokens_this_month: 0
  used_questions_this_month: 0
  reset_day: 1
```

Usage event:

```json
{
  "timestamp": "2026-05-15T10:00:00Z",
  "workspace_id": "clinic-a",
  "telegram_user_id": "222222",
  "task": "wiki_qa",
  "provider_mode": "managed",
  "model": "clinic-mini-default",
  "input_tokens": 1200,
  "output_tokens": 420,
  "total_tokens": 1620,
  "estimated_cost_usd": 0.0021,
  "status": "ok"
}
```

Quota behavior:

- reject requests when hard limit is reached
- warn admin at 80% and 100%
- cap maximum context size per Q&A request
- cap maximum output tokens
- use cheaper default models for budget plans
- support manual top-up before payment automation exists

## Managed Credits Gateway MVP

The external gateway can be small.

Required endpoints:

```text
POST /v1/generate
GET /v1/workspaces/{workspace_id}/usage
POST /v1/workspaces/{workspace_id}/quota-adjustments
```

`POST /v1/generate` request:

```json
{
  "workspace_id": "clinic-a",
  "user_id": "222222",
  "task": "wiki_qa",
  "model": "clinic-mini-default",
  "messages": []
}
```

Gateway responsibilities:

- authenticate workspace token
- check plan and quota
- map public model aliases to real provider models
- call provider with operator-owned API key
- return generated text and usage
- persist usage event
- never return provider keys

For the hosted mode, this gateway can start as internal Python code behind `WikiLLMClient`. For self-hosted managed credits, it must be a remote service.

## Installation Plan

### BYOK Deployment

1. Install Hermes Agent on a persistent server or VPS.
2. Install and enable the Hermes-wiki plugin.
3. Configure Telegram Gateway with BotFather token.
4. Configure `TELEGRAM_ALLOWED_USERS` or DM pairing.
5. Initialize the wiki workspace.
6. Configure provider/model and API key in the Hermes environment.
7. Add admin Telegram IDs to Hermes-wiki access config.
8. Add QA user Telegram IDs or group-level pairing flow.
9. Ingest initial documents with `/wiki-add` or CLI.
10. Test Q&A with source citations.
11. Install Hermes Gateway as a service.

### Hosted Managed Credits Deployment

1. Operator provisions a customer workspace on the operator server.
2. Operator creates Telegram bot or asks customer to create one and share only the bot token through a secure channel.
3. Operator configures Hermes Gateway for that bot.
4. Operator initializes Hermes-wiki workspace with `llm.mode=managed`.
5. Operator assigns plan quota such as `clinic_mini`.
6. Operator registers admin Telegram IDs.
7. Admin uploads or provides initial documents.
8. Operator runs ingest and Q&A validation.
9. Operator enables gateway service and monitoring.
10. Customer starts pilot through Telegram.

### Self-Hosted Managed Credits Deployment

1. Customer installs Hermes Agent on their own server.
2. Customer installs and enables Hermes-wiki plugin.
3. Operator provisions a managed workspace token.
4. Customer stores `HERMES_WIKI_MANAGED_TOKEN` in their Hermes environment.
5. Customer configures `llm.mode=managed` and `managed_endpoint`.
6. Customer configures Telegram Gateway.
7. Admin runs `/wiki-provider test`.
8. Admin ingests documents.
9. Plugin sends generation requests to operator managed gateway.
10. Operator gateway enforces quota and returns usage.

## Deployment Defaults For Clinic Pilots

Recommended low-cost pilot defaults:

```yaml
llm:
  mode: managed
  model: clinic-mini-default

qa:
  max_context_tokens: 8000
  max_output_tokens: 800
  require_citations: true
  refuse_without_source: true
  include_medical_disclaimer: true

access:
  admin_required_for_ingest: true
  qa_enabled_for_allowed_users: true
```

Recommended Telegram Gateway display:

```yaml
display:
  tool_progress: new
```

Recommended isolation:

```yaml
terminal:
  backend: docker
  container_cpu: 1
  container_memory: 5120
  container_persistent: true
```

## Implementation Phases

### Phase 1: Role-Gated Telegram MVP

- [ ] Add plugin access config loader for admins and QA users
- [ ] Add role-check helper that accepts Telegram user ID from Hermes Gateway context
- [ ] Gate existing admin commands behind admin role
- [ ] Add read-only `/ask` or `/wiki-ask` command
- [ ] Treat normal Telegram messages as Q&A only when safe in the gateway context
- [ ] Add denial messages for unauthorized admin commands

### Phase 2: Grounded Q&A

- [ ] Implement simple wiki retrieval over index, summaries, concepts, and source snippets
- [ ] Add Q&A prompt with source-only answering rules
- [ ] Add citation validation
- [ ] Add no-answer behavior when sources are insufficient
- [ ] Add medical disclaimer toggle
- [ ] Add tests for citation-required answers and no-source refusals

### Phase 3: Provider Mode Abstraction

- [ ] Add `WikiLLMClient` interface
- [ ] Route summary generation, concept generation, and Q&A through `WikiLLMClient`
- [ ] Preserve current Hermes `AIAgent` behavior for BYOK/local modes
- [ ] Add usage event logging for every generation task
- [ ] Add admin `/wiki-provider status` and `/wiki-provider test`

### Phase 4: Managed Credits MVP

- [ ] Add managed credits config fields
- [ ] Add quota checks before generation
- [ ] Add usage ledger after generation
- [ ] Add hard stop when quota is exceeded
- [ ] Add `/wiki-usage` and `/wiki-quota` admin commands
- [ ] Add manual monthly reset/top-up support
- [ ] Add model aliases for low-cost plans

### Phase 5: External Managed Gateway

- [ ] Build minimal authenticated `/v1/generate` service
- [ ] Store operator provider keys only on the gateway server
- [ ] Add workspace token authentication
- [ ] Add quota enforcement and usage persistence
- [ ] Add plugin client for `managed_endpoint`
- [ ] Add retry and clear error handling for gateway failures

### Phase 6: Production Hardening

- [ ] Add audit log viewer for admins
- [ ] Add backup/restore guide for `raw/`, `wiki/`, and `.hermeskb/`
- [ ] Add deployment checklist for systemd/launchd
- [ ] Add Docker Compose example for clinic pilot
- [ ] Add monitoring for gateway uptime and LLM spend
- [ ] Add redaction rules for secrets and patient identifiers in logs

## Security Requirements

- Never store provider API keys inside `wiki/` or `raw/`.
- Never return full provider keys through Telegram.
- Never trust LLM output for permission decisions.
- Always check admin permissions before write operations.
- Keep Q&A tool access disabled or read-only.
- Keep `AIAgent` generation deterministic where possible.
- Use `quiet_mode=True`, `skip_memory=True`, and `skip_context_files=True` for controlled wiki generation.
- Prefer Docker terminal backend for shared team bots.
- Keep audit logs append-only where practical.

## Testing Plan

Unit tests:

- role parsing from config and env
- admin allow/deny decisions
- QA allow/deny decisions
- provider mode resolution
- quota pre-checks
- usage ledger writes
- citation validator behavior
- no-source refusal behavior

Integration tests:

- admin can run status/list/config/add
- QA user cannot run add/config/rebuild
- QA user can ask a grounded question
- Q&A answer includes citations
- managed quota exhaustion blocks generation
- BYOK mode bypasses managed-credit deduction but still logs usage

Deployment smoke tests:

- Hermes Gateway starts with Telegram adapter
- authorized admin receives `/wiki-status`
- unauthorized Telegram user is blocked by gateway or plugin role check
- QA user receives cited answer
- managed credits usage increments after Q&A
- gateway restart preserves workspace and quota state

## Pricing-Oriented Plan Defaults

Managed plans should be budget-friendly but hard-limited.

Example internal mapping:

| Plan | Users | Questions/month | Token limit/month | Notes |
|---|---:|---:|---:|---|
| Trial | 3 | 50 | 200,000 | Short pilot |
| Clinic Mini | 10 | 500 | 2,000,000 | Small clinic |
| Clinic Basic | 20 | 2,000 | 8,000,000 | Active small team |
| Department Pilot | 50 | 5,000 | 25,000,000 | Hospital department pilot |

Expose customer-facing quota as questions/month. Track internal quota as tokens and estimated cost.

## Open Questions

- How should Hermes Gateway pass Telegram user metadata into plugin tools and slash commands?
- Should normal free-text Telegram messages route to `/wiki-ask` by default, or should Q&A require an explicit command in MVP?
- Should `wiki-list` be visible to QA users or admin-only for medical deployments?
- Should managed credits use SQLite from day one, or is append-only JSONL enough for hosted pilots?
- Which provider/model should back the first `clinic-mini-default` alias?

## Definition Of Done

- A clinic pilot can run one Telegram bot where normal members can only ask wiki questions.
- Admins can add documents, view status, list indexed content, and configure provider mode.
- All Q&A answers are grounded in wiki content and include citations.
- BYOK mode works without managed-credit deduction.
- Managed credits mode enforces quota before calling the provider.
- Usage is logged by workspace, Telegram user, task, model, and token count.
- The deployment guide covers hosted BYOK, hosted managed credits, and self-hosted managed credits.
