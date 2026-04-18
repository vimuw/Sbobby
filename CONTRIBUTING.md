# Contributing to El Sbobinator

## Prerequisites

| Tool | Required version |
|------|-----------------|
| Python | 3.11 (exact — matches CI) |
| Node.js | 24 (exact — matches CI) |
| pip | bundled with Python |
| npm | bundled with Node.js |

No `.env` or API key is needed to develop or build. Keys are entered at runtime inside the app's Settings screen.

## Install

```bash
# Install all dependencies (runtime + dev tools: ruff, pyinstaller, …)
python scripts/build_release.py deps --ui webui --dev

# Install git hooks (runs ruff, whitespace/EOF/YAML/JSON checks before every commit)
pre-commit install
```

## Test / check commands

```bash
# Verify all tooling and dependencies are present
python scripts/build_release.py deps --ui webui --dev

# Lint (ruff) + full test suite — skips npm install if already done
python scripts/build_release.py check --skip-npm-install
```

Run both before opening a PR. The CI gate runs the same commands.

## Build commands

```bash
# Windows
python scripts/build_release.py build --target windows --ui webui --install-deps --dev-deps

# macOS
python scripts/build_release.py build --target macos --ui webui --install-deps --dev-deps
```

## Where the code lives

| Path | What it is |
|------|-----------|
| `el_sbobinator/` | Python app and backend logic |
| `webui/` | React + TypeScript frontend |
| `scripts/build_release.py` | Authoritative automation entrypoint (lint, test, build, packaging) |
| `tests/` | unittest test suite |
| `docs/architecture.md` | Module map (Python + frontend) and runtime flow |
| `docs/pipeline.md` | Pipeline phases, model fallback chain and `last_error` values |
| `docs/session_model.md` | On-disk session layout and `session.json` schema |
| `docs/bridge_protocol.md` | Python ↔ React event/API contract |

## PR expectations

- All checks must pass: `python scripts/build_release.py check --skip-npm-install` exits 0.
- Keep commits focused; one logical change per PR.
- If you add behaviour, add a test.
- Do not weaken or delete existing tests.

## Recommended commands (quick reference)

```bash
# One-shot: verify deps, lint, test
python scripts/build_release.py deps --ui webui --dev
python scripts/build_release.py check --skip-npm-install
```
