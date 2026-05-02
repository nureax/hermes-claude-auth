---
title: hermes-claude-auth — Analysis, Gaps & Improvement Roadmap
tags: [research, hermes, anthropic, oauth, bypass, claude-auth]
aliases: [hermes-auth-analysis]
created: 2026-05-02
---

# hermes-claude-auth — Analysis, Gaps & Improvement Roadmap

## Purpose

This document captures a full analysis of the current state of `hermes-claude-auth` (v1.1.1) as of 2026-05-02, documents what is broken, and provides a concrete improvement roadmap with implementation specifics.

This is a living document. Update it when upstream opencode-claude-auth ships new PRs or when Anthropic rotates validation signals again.

---

## What the Tool Does

`hermes-claude-auth` monkey-patches `hermes-agent`'s `agent.anthropic_adapter.build_anthropic_kwargs` at import time (via `sitecustomize.py` + `MetaPathFinder`) to make OAuth-authenticated requests pass Anthropic's server-side content validation. It allows Claude Max/Pro subscribers to use their subscription quota with hermes-agent instead of paying per-token extra usage.

Install is non-destructive — no hermes-agent source files are modified. Uninstall by removing the sitecustomize hook.

---

## Current Version State

| Field | Value |
|-------|-------|
| Current version | v1.1.1 (2026-04-22) |
| Upstream opencode-claude-auth | v1.5.3 (2026-04-30) |
| Upstream hermes-auth issues | #7, #9, #10, #11 document the gaps |
| Status as of 2026-05-02 | **BROKEN** — Anthropic validator updated 2026-04-28 |
| Target CC version | 2.1.123 (current local: 2.1.126) |

---

## What's Broken (v1.1.1 vs Current Anthropic Validator)

### CRITICAL — causes "Third-party apps" 400 on every request

**1. SDK identity string is stale (Issue #10, Fix #1)**

`_SYSTEM_IDENTITY` in v1.1.1:
```python
_SYSTEM_IDENTITY = "You are Claude Code, Anthropic's official CLI for Claude."
```

Current Claude Code 2.1.123+ uses:
```python
_SYSTEM_IDENTITY = "You are a Claude agent, built on Anthropic's Claude Agent SDK."
```

Anthropic's validator inspects `system[1].text` for this exact string. The old string is now a **third-party flag**. Additionally, the new identity block requires `cache_control: {"type": "ephemeral", "ttl": 3600}`.

**2. Stainless headers double-sent with wrong case (Issue #10, Fix #2)**

The Anthropic Python SDK automatically injects `X-Stainless-Lang: python` etc. via `BaseClient._merge_mappings`. The patch sent overrides as `x-stainless-lang: js` (lowercase). httpx serialises both as `x-stainless-lang: python, js` — instant third-party fingerprint.

Fix: use the SDK's exact PascalCase (`X-Stainless-Lang`, `X-Stainless-Runtime`, etc.) so `_merge_mappings` actually replaces rather than appends. Also strip Python-only Stainless fields via `anthropic.lib.streaming.Omit()`:
- `X-Stainless-Async`
- `X-Stainless-Helper-Method`
- `X-Stainless-Stream-Helper`
- `x-stainless-helper`
- `x-stainless-read-timeout`

**3. PascalCase tool names now blocked (Issue #7, upstream PR #193)**

Anthropic updated its validator ~2026-04-24 to blacklist both lowercase `mcp_bash` AND PascalCase `mcp_Bash` tool name patterns.

Fix: MD5-based obfuscation — all tool names become `t_<md5[:8]>`, e.g. `mcp_bash` → `t_a1b2c3d4`. A bidirectional map restores originals from responses. Hashed names are blacklist-proof. Strip the `mcp_` prefix before hashing so the hash is stable regardless of hermes's prefixing.

**4. Missing `metadata.user_id` (Issue #10, Fix #5)**

Real Claude Code injects JSON-encoded `{device_id, account_uuid, session_id}` as `metadata.user_id`. Anthropic's validator cross-references `account_uuid` against the OAuth token's account claim.

Source: `~/.claude.json`:
```json
{
  "userID": "<device_id>",
  "groveConfigCache": {"<account_uuid>": {...}}
}
```

Implementation:
```python
import json, uuid
from pathlib import Path

def _read_claude_json_ids():
    try:
        data = json.loads(Path.home() / ".claude.json").read_text())
        device_id = data.get("userID", "")
        account_uuid = next(iter(data.get("groveConfigCache", {})), "")
        return device_id, account_uuid
    except Exception:
        return "", ""

def _build_user_id_metadata(session_id: str) -> str:
    device_id, account_uuid = _read_claude_json_ids()
    return json.dumps({"device_id": device_id, "account_uuid": account_uuid, "session_id": session_id})
```

Inject as: `api_kwargs["metadata"] = {"user_id": _build_user_id_metadata(_SESSION_ID)}`

**5. Wrong User-Agent format (Issue #10, Fix #3)**

Current: Hermes's own user-agent string.  
Required: `claude-cli/<version> (external, sdk-cli)`

Example: `claude-cli/2.1.126 (external, sdk-cli)`

**6. Stale Node runtime version (Issue #10, Fix #3)**

`_STAINLESS_NODE_VERSION` hardcoded to `v22.11.0`. Current Claude Code 2.1.123+ reports `v24.3.0`.

**7. Missing per-session UUID header (Issue #10, Fix #3)**

`x-claude-code-session-id` must be a fresh UUID4 per Python process. Real Claude Code generates this on startup.

---

### MEDIUM — missing features causing extra-usage routing on some models/requests

**8. Beta flags stale (Issue #10, Fix #4)**

Add to `_EXTRA_OAUTH_BETAS`:
- `context-1m-2025-08-07`
- `context-management-2025-06-27`
- `effort-2025-11-24`

Remove from `_EXTRA_OAUTH_BETAS`:
- `interleaved-thinking-2025-05-14` (hermes already includes it via `oauth_safe_common`, patch was creating a duplicate)

**9. Tool name shape wrong for latest validator (Issue #11)**

Beyond MD5 obfuscation, the current validator expects tool names in the `mcp__SERVER__TOOL` namespace format. The current patch uses flat `t_<hash>` obfuscation but doesn't namespace them correctly.

The hermes-auth Issue #11 approach: wrap as `mcp__hermes__<name>` (namespace = `hermes`). This mirrors the `mcp__SERVER__TOOL` convention real MCP servers use.

Tradeoff vs MD5: MD5 is more blacklist-resistant but harder to debug. The `mcp__hermes__` namespace is more transparent and may be all that's needed for now.

**10. Missing `AnthropicTransport.normalize_response` hook (Issue #11)**

Hermes 0.11.0+ refactored the adapter — `normalize_anthropic_response` is now on `AnthropicTransport.normalize_response`. The current response unhook targets the old function and silently becomes a no-op on newer hermes versions.

Fix: detect and patch both `normalize_anthropic_response` (legacy) and `AnthropicTransport.normalize_response` (new) with a fallback priority chain.

**11. Adaptive thinking fields missing for Opus 4.6/4.7 (Issue #10, Fix #6)**

Real Claude Code sends `thinking: {"type": "adaptive"}` for Opus 4.x models. This should be injected via `extra_body` (Python SDK ≤ 0.96 doesn't accept it as a typed kwarg but forwards `extra_body` verbatim).

Also: `context_management` (`clear_thinking_20251015 / keep: all`) and `output_config` (`effort: xhigh`) via `extra_body`.

**12. Opus 4.7 not in adaptive thinking model list (upstream v1.5.0)**

`_model_supports_adaptive_thinking` checks for `"4-6"` and `"4.6"`. Add `"4-7"` and `"4.7"`.

---

### LOW — non-functional improvements

**13. No drift detection / health check mode**

There's no way to verify the bypass is actually working before sending real requests. A `--verify` flag or diagnostic smoke test would help users detect the next Anthropic validator update immediately.

**14. No automatic Claude Code version tracking**

`_STAINLESS_PACKAGE_VERSION`, `_STAINLESS_NODE_VERSION`, and `_BILLING_ENTRYPOINT` are all hardcoded. They need updates every time Claude Code ships a new version that changes these values. Ideally these would be read from the actual `claude` binary or its bundled package metadata.

**15. No retry handling for out-of-extra-usage (upstream v1.5.2)**

When `extra usage` is exhausted (distinct from subscription quota being depleted), upstream opencode-claude-auth detects the specific error string and caps the retry-after delay. Currently hermes-claude-auth passes this error through to hermes's default error handling.

---

## Implementation Priority Queue

| Priority | Change | Effort | Impact |
|----------|--------|--------|--------|
| P0 | Fix `_SYSTEM_IDENTITY` string | Trivial | Unblocks all OAuth requests |
| P0 | Fix Stainless header case + strip Python-only headers | Medium | Stops double-send fingerprint |
| P0 | Replace PascalCase with MD5/namespace obfuscation | Medium | Stops tool-name flagging |
| P0 | Add `metadata.user_id` from `~/.claude.json` | Low | Account UUID cross-reference |
| P0 | Fix User-Agent format | Trivial | Minor signal |
| P0 | Bump Node runtime version to `v24.3.0` | Trivial | Fingerprint accuracy |
| P0 | Add per-session UUID header | Trivial | Required field |
| P1 | Refresh beta flags | Trivial | Model routing |
| P1 | Add AnthropicTransport hook (hermes 0.11.0+) | Medium | Response unwrapping |
| P1 | Add Opus 4.7 to adaptive thinking list | Trivial | Model support |
| P2 | Add adaptive thinking/context fields via extra_body | Medium | Routing accuracy |
| P2 | Out-of-extra-usage error detection + retry cap | Low | UX improvement |
| P3 | Drift detection / health check mode | High | Maintainability |
| P3 | Dynamic version tracking from `claude` binary | Medium | Maintenance reduction |

---

## Implementation Notes

### Reading ~/.claude.json

`~/.claude.json` holds the local Claude Code device and account identifiers. On the local machine (2026-05-02):
- `userID` → device_id (8ec7925e...)
- `groveConfigCache` first key → account_uuid (4f68aebf...)

Cache the read at module import time; fail silently if the file is missing.

### Stainless Header Fix (Critical Detail)

The Anthropic Python SDK's `BaseClient._merge_mappings` uses case-insensitive header matching when the value is an `httpx.Headers` object, but **not** when it's a plain dict. Since the patch passes `extra_headers` as a plain dict, the merge uses exact key comparison. Sending `x-stainless-lang` when the SDK sends `X-Stainless-Lang` results in both being included.

Fix options:
1. Use the exact same casing as the SDK: `X-Stainless-Lang`, `X-Stainless-Runtime`, `X-Stainless-Runtime-Version`, `X-Stainless-Package-Version`, `X-Stainless-OS`, `X-Stainless-Arch`
2. For Python-only fields to suppress, set them to `anthropic.NOT_GIVEN` or use `Omit()` from `anthropic._types`

### Tool Name Obfuscation Stability

If using MD5 (`t_<hash>`): hash `tool_name.removeprefix("mcp_")` (not the full prefixed name) so the hash is consistent regardless of hermes's internal prefix state. The reverse map must be populated before the request is sent and referenced during response normalization.

If using `mcp__hermes__<name>` namespace: strip any existing `mcp_` or `mcp__` prefix before wrapping to avoid `mcp__hermes__mcp_bash` accidents.

---

## Version History (for this tool)

| Version | Date | What Changed |
|---------|------|-------------|
| 1.0.0 | 2026-04-09 | Billing header, system prompt relocation, prompt-caching beta, aux-client temp hook |
| 1.1.0 | 2026-04-22 | PascalCase mcp_ tools, sdk-cli entrypoint, advisor-tool beta, Stainless spoof headers, ?beta=true |
| 1.1.1 | 2026-04-22 | Installer only: macOS Keychain auto-mirror |
| **1.2.0 (needed)** | — | MD5 tool name obfuscation (replaces PascalCase, which Anthropic blocked ~2026-04-24) |
| 1.4.0 | 2026-05-02 | Implemented fingerprint corrections for CC 2.1.123+: SDK identity, exact-case Stainless headers, User-Agent/session UUID, metadata.user_id, beta refresh, tool namespace, Hermes transport unwrap |
| **1.5.x (needed)** | — | Opus 4.7, out-of-extra-usage retry cap |

---

## Upstream References

- **hermes-claude-auth repo**: https://github.com/kristianvast/hermes-claude-auth
- **opencode-claude-auth (source)**: https://github.com/griffinmartin/opencode-claude-auth
- **Issue #7 (MD5 tools)**: https://github.com/kristianvast/hermes-claude-auth/issues/7
- **Issue #9 (blocked 2026-04-28)**: https://github.com/kristianvast/hermes-claude-auth/issues/9
- **Issue #10 (v1.4.0 fix)**: https://github.com/kristianvast/hermes-claude-auth/issues/10
- **Issue #11 (hermes 0.11.0 transport hook)**: https://github.com/kristianvast/hermes-claude-auth/issues/11
- **opencode PR #193 (MD5 obfuscation)**: https://github.com/griffinmartin/opencode-claude-auth/pull/193
- **opencode PR #207 (CC 2.1.112 fingerprint)**: https://github.com/griffinmartin/opencode-claude-auth/pull/207

---

## Related KB Notes

- [[hermes-anthropic-extra-usage-400]]
- [[hermes-anthropic-400-obfuscation-fix]]
- [[hermes-claude-pro-oauth-429-2026-05-02]]
- [[hermes-agent]]
