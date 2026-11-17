# AGENTS.md

Sublime Text LSP client that manages the [nimlangserver](https://github.com/nim-lang/langserver) binary.
No build step and no Python dependencies: `plugin.py` runs inside Sublime Text's embedded Python 3.14 plugin
host and imports `sublime` and `LSP.plugin` from packages that only exist at runtime (the legacy Python 3.3
host is disabled).

Reference checkouts, if present next to this repo:
- `../LSP` (sublimelsp/LSP) — provides the `LSP.plugin` API. Verify imports (`LspPlugin`, `ClientConfig`,
  `OnPreStartContext`, `PluginStartError`) against `plugin/api.py` and `plugin/__init__.py` there.
- `../langserver` (nim-lang/langserver) — server source of truth for settings: the `NlsConfig` object in
  `ls.nim` and the settings table in `book/src/lsp.md`.

## Layout

- `plugin.py` — the entire plugin: resolves/downloads/updates the server binary and starts it through the LSP
  `LspPlugin` API (`on_pre_start_async`, `needs_update_or_installation`, `install_or_update`, ...).
- `LSP-nimlangserver.sublime-settings` — defaults, including every option forwarded to nimlangserver.
- `sublime-package.json` — JSON schema for those same settings (global file and `.sublime-project`
  overrides). A setting added/removed/renamed in the `.sublime-settings` file must be mirrored here and
  vice versa.
- Sublime resource files are JSON-with-comments (comments, trailing commas); Sublime Text parses them but
  strict JSON tools (`python -m json.tool`) reject them.
- `tests/smoke/` — smoke test fixtures (see below).
- `messages.json` + `messages/*.md` — Package Control upgrade notices keyed by package version; add an
  entry for user-visible/breaking changes.
- `README.md` ships to users; keep developer notes out of it.

## Verification

- Lint: `ruff check .` — config in `pyproject.toml`: Python 3.14, 110 columns, preview rules, single-line
  sorted imports. The isort config requires `from __future__ import annotations` in every module (style
  rule, not needed at runtime on 3.14).
- Typecheck: `pyright` — config in `pyproject.toml`, but expect unresolved-import errors for `sublime` and
  `LSP.plugin` (no stubs in this repo); don't chase them.
- Neither ruff nor pyright runs in CI; there is no Python test suite.
- The only automated test is `.github/workflows/smoke-test.yml`, which runs `tests/smoke/smoke.yaml` through
  `sublimelsp/lsp_smoke_test@v1` on Linux/macOS/Windows, installing Nim and the NimLime package (provides
  the `source.nim` scope the server is enabled for). It checks that `sample.nim` (`echo missingName`)
  produces an "undeclared identifier" diagnostic; the fixture sets `binary: ''` so the managed server is
  downloaded and enables `nim.autoCheckFile` because v1.18.0 disables on-the-fly checks by default. Running
  it requires Sublime Text, so verify through the workflow / a real Sublime Text install rather than
  inventing a headless command.

## Gotchas

- `VERSION` in `plugin.py` is the nimlangserver release tag to download; Renovate bumps it via the custom
  manager in `renovate.json` and does not touch settings. For every bump, diff the released `NlsConfig`
  fields and default values against `LSP-nimlangserver.sublime-settings` and `sublime-package.json` and
  update both. Settings are added, removed, and get new defaults between releases: v1.18.0 removed
  `nim.autoRestart` and flipped `nim.autoCheckFile` to `false`. Diff the full set, not just additions.
- Startup raises `PluginStartError` if `nim` is not on PATH, and requires nimlangserver >= 1.2.0.
- `binary` semantics: non-empty → use that executable from PATH; empty → download/update the managed server
  into the package storage directory.
- Project overrides live under `settings.LSP.LSP-nimlangserver` (the key was renamed from `nimlangserver`
  in 2.0.0).
- `.gitattributes` `export-ignore` entries keep dev-only files out of the Package Control release; add new
  dev files there.
