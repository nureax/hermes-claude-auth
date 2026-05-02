---
title: hermes-claude-auth TODO
tags: [hermes, claude, auth, oauth, todo]
aliases: [hermes-claude-auth-continuation, claude-auth-todo]
created: 2026-05-02
---

# hermes-claude-auth TODO

Continuation note for the next session. This project maintains the Hermes/Claude OAuth compatibility patch used to reduce HTTP 429 behavior by aligning Hermes Anthropic SDK requests with current Claude Code traffic.

## Current State

- Local project: `/home/cj/AI-Knowledge-Base/hermes-claude-auth`
- Maintained fork: `https://github.com/nureax/hermes-claude-auth`
- Original upstream: `https://github.com/kristianvast/hermes-claude-auth`
- Main KB repo: `https://github.com/nureax/AI-Knowledge-Base`
- Installed runtime patch: `/home/cj/.hermes/patches/anthropic_billing_bypass.py`
- Installed sitecustomize hook: `/home/cj/.hermes/hermes-agent/venv/lib/python3.11/site-packages/sitecustomize.py`
- Hermes gateway service: `hermes-gateway.service`
- Latest implementation commit in fork: `e1e29f6 feat: sync Claude OAuth fingerprint to CC 2.1.123`
- Latest documented installed version: `1.4.0`
- Claude Code version observed during implementation: `2.1.126`
- Anthropic Python package observed in Hermes agent venv: `0.86.0`

## Completed in Previous Session

- Compared the local patch against upstream/related Claude OAuth auth behavior.
- Documented architecture, validator drift, and roadmap in:
  - [[ANALYSIS]]
  - [[RESEARCH]]
  - [[hermes-auth-research]]
- Implemented v1.4.0 fingerprint updates:
  - SDK identity string: `You are a Claude agent, built on Anthropic's Claude Agent SDK.`
  - `cache_control`: `{"type": "ephemeral", "ttl": "1h"}`
  - Claude Code style `User-Agent`: `claude-cli/<version> (external, sdk-cli)`
  - JS/Node Stainless headers instead of Python SDK fingerprints
  - account UUID/session metadata from `~/.claude.json`
  - `mcp__hermes__<tool>` tool-name wrapping and response restoration
  - Hermes transport response normalization compatibility
  - Opus 4.7 adaptive-thinking temperature handling
- Tests passed:
  - `40 passed`
  - `py_compile` passed for source and installed runtime copies
- Installed patch locally with `./install.sh`.
- Restarted Hermes gateway; service was active and logs showed bypass installed.
- Pushed fork and KB commits.
- Logged cache-control TTL learning in `.learnings/patterns.md`.

## Immediate Next Steps

1. Run live smoke tests after Claude quota/rate limit reset.

   ```bash
   hermes chat -q 'Reply with exactly: AUTH TEST OK' --provider anthropic -m claude-sonnet-4-6 -Q
   hermes chat -q 'List files in the current directory using your tools.' --provider anthropic -m claude-sonnet-4-6 -Q
   ```

2. If smoke tests pass, document result in this note and `.learnings/patterns.md`.

3. If smoke tests fail with HTTP 429 or validator errors:
   - Capture exact status code, response body, request model, and relevant sanitized headers.
   - Do not log OAuth tokens or credential values.
   - Compare current generated request shape against latest Claude Code traffic.
   - Update tests first, then patch implementation.

4. Optional: open PR from `nureax/hermes-claude-auth` to `kristianvast/hermes-claude-auth` after live verification.

5. Optional: re-index the KB after further bulk edits:

   ```bash
   cd /home/cj/AI-Knowledge-Base
   ~/.local/share/kb-rag-venv/bin/python3 scripts/kb-index.py
   ```

## Useful Commands

### Repo checks

```bash
cd /home/cj/AI-Knowledge-Base/hermes-claude-auth
git status --short
git log --oneline -5
git remote -v
```

### Tests

```bash
cd /home/cj/AI-Knowledge-Base/hermes-claude-auth
/home/cj/AI-Knowledge-Base/hermes-agent/.venv/bin/python -m pytest tests -q
python3 -m py_compile anthropic_billing_bypass.py sitecustomize_hook.py
```

### Install patch locally

```bash
cd /home/cj/AI-Knowledge-Base/hermes-claude-auth
./install.sh
systemctl --user is-active hermes-gateway.service
journalctl --user -u hermes-gateway.service -n 50 --no-pager
```

### Verify installed runtime copy

```bash
python3 -m py_compile /home/cj/.hermes/patches/anthropic_billing_bypass.py /home/cj/.hermes/hermes-agent/venv/lib/python3.11/site-packages/sitecustomize.py
```

## Known Caveats

- Claude Code was rate-limited during implementation, so no live network smoke test was run at that time.
- Do not preserve or document actual credential/token values from `~/.claude.json`.
- Main KB repo treats `hermes-claude-auth` as a submodule/independent repo. Commit inside the submodule first, then commit the submodule pointer in the KB repo.
- Push implementation to the `nureax` remote/fork; direct push to `kristianvast/hermes-claude-auth` is not available.
- Main KB currently may show unrelated local modification in `hermes-agent`; do not include that in project commits unless intentionally working on Hermes itself.

## Commit Flow

```bash
cd /home/cj/AI-Knowledge-Base/hermes-claude-auth
git add anthropic_billing_bypass.py tests/test_bypass.py README.md ANALYSIS.md RESEARCH.md TODO.md
git commit -m '<message>'
git push nureax main

cd /home/cj/AI-Knowledge-Base
git add hermes-claude-auth research/hermes-auth-research.md research/index.md .learnings/patterns.md
git commit -m '<message>'
git push origin master
```

## References

- [[ANALYSIS]]
- [[RESEARCH]]
- [[hermes-auth-research]]
- [[index]]
