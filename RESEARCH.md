---
title: hermes-claude-auth Research — Auth Bypass Architecture & Anthropic Validator Signals
tags: [research, anthropic, oauth, hermes, bypass]
aliases: [hermes-auth-research]
created: 2026-05-02
---

# hermes-claude-auth Research — Anthropic OAuth Validator Signals

## Overview

This is a reference for understanding how Anthropic's server-side OAuth validation works and which signals it uses to distinguish "real Claude Code" from third-party clients. It consolidates findings from opencode-claude-auth PRs, hermes-claude-auth issues, and local request capture analysis.

## Anthropic's Validation Model (as of 2026-04-30)

Anthropic runs server-side validation on `/v1/messages` requests authenticated via OAuth (Claude Code subscription tokens). Requests from non-official clients are either:

1. **Hard-rejected** with HTTP 400: "Third-party apps now draw from your extra usage"
2. **Soft-routed** into extra-usage billing lane (HTTP 429 when that's exhausted)

The validator is not open-source. All knowledge below is reverse-engineered from error responses, wire captures, and upstream bypass implementations.

## Validated Signals (all must match simultaneously)

### System Prompt Structure

| Field | Expected value |
|-------|---------------|
| `system[0].type` | `"text"` |
| `system[0].text` | Begins with `"x-anthropic-billing-header: "` |
| `system[1].type` | `"text"` |
| `system[1].text` | `"You are a Claude agent, built on Anthropic's Claude Agent SDK."` (changed from "Claude Code" in CC ~2.1.120) |
| `system[1].cache_control` | `{"type": "ephemeral", "ttl": 3600}` |
| All other system entries | Must be relocated to `system-reminder` blocks in first user message |

### Billing Header Format

```
x-anthropic-billing-header: cc_version=<version>.<3-char-suffix>; cc_entrypoint=sdk-cli; cch=<5-char-sha256>;
```

Where:
- `<version>` = Claude CLI version string (e.g. `2.1.126`)
- `<3-char-suffix>` = `SHA256(salt + msg[4] + msg[7] + msg[20] + version)[:3]`
- `salt` = `"59cf53e54c78"` (hardcoded in Claude Code binary)
- `msg[i]` = character at index i of first user message text (padding `"0"` if short)
- `cch` = `SHA256(first_user_message_text)[:5]`
- `cc_entrypoint` = `"sdk-cli"` (was `"cli"` before CC 2.1.112)

### HTTP Headers

| Header | Expected value | Notes |
|--------|---------------|-------|
| `User-Agent` | `claude-cli/<version> (external, sdk-cli)` | e.g. `claude-cli/2.1.126 (external, sdk-cli)` |
| `X-Stainless-Lang` | `js` | NOT `python` — this is the tell |
| `X-Stainless-Runtime` | `node` | |
| `X-Stainless-Runtime-Version` | `v24.3.0` | was `v22.11.0` in CC ≤ 2.1.112 |
| `X-Stainless-Package-Version` | `0.81.0` | @anthropic-ai/sdk version |
| `X-Stainless-OS` | `MacOS` / `Linux` / `Windows` | real platform |
| `X-Stainless-Arch` | `x64` / `arm64` / etc | real arch |
| `X-Stainless-Retry-Count` | `"0"` | |
| `X-Stainless-Timeout` | `"600"` | |
| `anthropic-dangerous-direct-browser-access` | `"true"` | |
| `x-claude-code-session-id` | UUID4, fresh per process | |

**Python-only headers to suppress** (set via `Omit()` sentinel):
- `X-Stainless-Async`
- `X-Stainless-Helper-Method`
- `X-Stainless-Stream-Helper`
- `x-stainless-helper`
- `x-stainless-read-timeout`

**Critical**: send header names in the exact case above. The Anthropic SDK uses `BaseClient._merge_mappings` which does exact key comparison for plain dict `extra_headers`. Wrong case = both the Python SDK's value and your override end up in the request (e.g. `x-stainless-lang: python, js`).

### Request Metadata

```json
{
  "metadata": {
    "user_id": "{\"device_id\": \"<~/.claude.json .userID>\", \"account_uuid\": \"<first key of .groveConfigCache>\", \"session_id\": \"<uuid4 per process>\"}"
  }
}
```

The `account_uuid` is cross-referenced against the OAuth token's account claim on Anthropic's server. If they don't match, the request is flagged.

### Query Parameter

`?beta=true` on `/v1/messages` — inject via `extra_query: {"beta": "true"}`.

### Tool Name Format

The validator inspects tool names in the `tools[]` array. Evolution of constraints:

| Period | Format | Status |
|--------|--------|--------|
| Before 2026-04-14 | `mcp_bash` (lowercase) | Was OK, now blocked |
| 2026-04-14 to ~2026-04-24 | `mcp_Bash` (PascalCase after prefix) | Was OK, now blocked |
| 2026-04-24+ | MD5 obfuscation `t_<8hex>` or `mcp__SERVER__TOOL` namespace | Current working approach |

**MD5 obfuscation approach** (hermes-auth Issue #7, opencode PR #193):
```python
import hashlib

_TOOL_NAME_OBF_MAP = {}  # obfuscated_name -> original_name
_TOOL_NAME_REV_MAP = {}  # original_name -> obfuscated_name

def obfuscate_tool_name(name: str) -> str:
    # Strip mcp_ prefix before hashing for stability
    base = name.removeprefix("mcp_")
    obf = "t_" + hashlib.md5(base.encode()).hexdigest()[:8]
    _TOOL_NAME_OBF_MAP[obf] = name
    _TOOL_NAME_REV_MAP[name] = obf
    return obf

def restore_tool_name(obf: str) -> str:
    return _TOOL_NAME_OBF_MAP.get(obf, obf)
```

**Namespace approach** (hermes-auth Issue #11):
```python
def namespace_tool_name(name: str) -> str:
    # Strip any existing prefix before wrapping
    base = name.removeprefix("mcp__").removeprefix("mcp_")
    return f"mcp__hermes__{base}"

def restore_namespaced_name(namespaced: str) -> str:
    prefix = "mcp__hermes__"
    if namespaced.startswith(prefix):
        return namespaced[len(prefix):]
    # lowercase first char if it got PascalCased
    if namespaced and namespaced[0].isupper():
        return namespaced[0].lower() + namespaced[1:]
    return namespaced
```

### Beta Flags (as of CC 2.1.123)

Send via `anthropic-beta` header (comma-joined):
- `claude-code-20250219` (hermes sends this natively)
- `oauth-2025-04-20` (hermes sends this natively)
- `prompt-caching-scope-2026-01-05`
- `advisor-tool-2026-03-01`
- `context-1m-2025-08-07`
- `context-management-2025-06-27`
- `effort-2025-11-24`

Do NOT add `interleaved-thinking-2025-05-14` — hermes already includes it via `oauth_safe_common`, adding it again creates a duplicate entry.

### Adaptive Thinking Fields (Opus 4.6 / 4.7)

For models matching `"4-6"`, `"4.6"`, `"4-7"`, `"4.7"` in the model string:
- Strip non-1 temperature (HTTP 400 otherwise)
- Inject via `extra_body`: `{"thinking": {"type": "adaptive"}, "context_management": {"type": "clear_thinking_20251015", "keep": "all"}, "output_config": {"effort": "xhigh"}}`

---

## Hermes-Agent Adapter Architecture Notes

### hermes ≤ 0.10.x (current on Ainzsrv)

- Main patch point: `agent.anthropic_adapter.build_anthropic_kwargs(is_oauth: bool, ...)`
- Response normalization: `agent.anthropic_adapter.normalize_anthropic_response(response, strip_tool_prefix: bool)`
- Tool prefix management: hermes prefixes tool names with `mcp_` internally before calling `build_anthropic_kwargs`

### hermes 0.11.0+

- Transport layer refactored: `agent.transports.anthropic.AnthropicTransport.normalize_response`
- The old `normalize_anthropic_response` function no longer exists — response unhook targeting it becomes a no-op
- Must detect hermes version and patch the appropriate location

### Patch Hook Chain

```
Python startup
  → sitecustomize.py (MetaPathFinder registered)
    → agent.anthropic_adapter imported
      → apply_patches() called
        → build_anthropic_kwargs wrapped (request bypass)
        → normalize_anthropic_response wrapped OR AnthropicTransport.normalize_response wrapped (response tool name restoration)
        → aux_client_hook installed (temperature fix for OAuth adaptive models)
```

---

## Failure Mode Reference

| HTTP Error | Message | Root Cause |
|-----------|---------|------------|
| 400 | "Third-party apps now draw from your extra usage, not your plan limits" | Validator fingerprint mismatch — any of the above signals wrong |
| 400 | "You're out of extra usage. Add more at claude.ai/settings/usage" | Extra usage credits depleted (distinct from plan quota) |
| 400 | "Extra inputs are not permitted" | Tool schema format wrong — usually the tool name namespace issue |
| 400 | unknown temperature error | Non-1 temperature on Opus 4.6/4.7 adaptive model |
| 429 | "Extra usage is required for long context requests" | Request classified as extra-usage-required; Anthropic routing issue |

---

## Maintenance Triggers

Update the bypass whenever:
1. `claude --version` reports a new minor version (e.g. 2.1.127+)
2. Anyone reports a new "Third-party apps" 400 error that starts universally
3. Upstream opencode-claude-auth ships a new release
4. New hermes-agent release changes `agent.anthropic_adapter` interface

Quick verification command:
```bash
hermes chat -q 'Reply with exactly: AUTH TEST OK' --provider anthropic -m claude-sonnet-4-6 -Q
```
