# Changelog

## [Unreleased]

### Added
- Cinema vision screenshots use SubLLM `autogrammar-nexu/vision`. YAML custom
  text models stay on LiteLLM so existing model-override tests keep working.
- `verify_capsule` now optionally runs `redup` (code duplication) and `vallm` (static
  code validation: syntax/imports/complexity, no LLM calls by default) against a
  capsule's source, via `RedupDuplicatesCheck`/`VallmValidationCheck`
  (`contracts/verify/duplicates.py`, `contracts/verify/llm_code_validation.py`). Both are
  purely additive and gracefully degrade to zero findings when the packages aren't
  installed — neither is a core dependency; declared as a new `full` extra
  (`pip install nexu[full]`). Verified: findings appear correctly against a real example
  capsule when installed, and cleanly disappear (simulated via `sys.modules[name] = None`)
  with no errors anywhere in the `verify_capsule` pipeline when absent; full test suite
  (258 tests) passes both ways.

### Fixed
- Cinema `/iterate`: scope- or hint-only iterations (e.g. `focus_scope: "colors"` with no
  KEEP/DELETE marks) rewrote `alt_a/b/c.html` via `apply_options` without ever appending a
  ledger entry — the ledger gate (`if keep_els or delete_els`) didn't account for this
  write path, so those mutations left no audit trail. Fixed by also gating on
  `options_written` (`server.py.tmpl`). This alone would have defeated the options cache
  (`options_cache_key` hashes the raw ledger, so appending an entry after every request
  would invalidate the very next identical request's cache lookup) — fixed first by
  excluding audit-only, no-op entries (empty keep/delete/proposed_contracts) from the
  cache-key computation (`cinema_options_cache.py`). Verified: a live subprocess Cinema
  server now writes a ledger entry for a scope-only `/iterate` call, and a second
  identical call still hits the options cache (`proposed_options_cached`); full test
  suite (258 tests, including all 17 `test_cinema_server.py` subprocess/integration
  tests) passes.

### Added
- `verify_capsule_workspace` now runs a Cinema-specific distinctness validator
  (`cinema_policy/workspace_verify.py`) that flags stale Option A/B/C previews — when
  `stage0/1/2.html` have diverged but `alt_a/b/c.html` haven't been refreshed to match.
  Previously this exact staleness check (`stage_files_are_distinct` +
  `option_previews_are_distinct`) only existed as an internal auto-fix trigger in
  `cinema_projects.py`; it's now also a reportable finding (`option_previews_stale` warn /
  `option_previews_distinctness` pass) surfaced through the same report the Cinema policy
  panel already displays. Verified against a real example capsule (found genuinely stale
  previews) and a synthetic one with matching previews (reports pass).
- `CapsuleGoalCheck` (`contracts/verify/capsule_goal.py`): surfaces a capsule's own
  top-level `scope: capsule` contract (its overarching intent) and whether the
  sub-intents it `require`s are declared elsewhere in the manifest. Purely additive and
  optional — a capsule without a `scope: capsule` contract gets no new finding and
  verification/promotion behave exactly as before. Uses the same warn-not-fail severity
  as the existing `required_intents` check, so it does not introduce a new promotion
  blocker (promotion is already gated on overall `verification.status == "pass"` for
  every capsule today). Verified with a capsule missing its declared sub-intents (warn)
  and one satisfying them (pass).

### Fixed
- Declared `intract>=0.5.14` as a proper `dependencies` entry in `pyproject.toml`. Nexu's
  contract checking (`verify_capsule`, cinema policy) previously relied on `intract` being
  a sibling checkout on disk with a `sys.path` fallback if the plain `import intract` failed
  — a fresh `pip install nexu` (e.g. in CI or on another machine) had no way to pull in
  `intract` and would silently degrade to `"intract package required"` errors. Verified with
  a fully isolated venv (no sibling `intract/` checkout): `pip install -e .` now pulls in
  `intract` automatically, and both the full test suite and `nexu capsule verify` produce
  identical results to the sibling-checkout dev setup.

### Refactor
- Introduced `nexu.contracts` as the intent-contract engine boundary. Moved
  `intract_adapter.py` to `contracts/adapter.py` (sibling-package discovery +
  `check_intract_policy`; `intract_adapter.py` is now a compatibility re-export).
- Split `verify.py`'s capsule verification into `contracts/verify/` — a `CapsuleCheck`
  protocol (`context.py`) plus one small module per check (`contracts_presence`,
  `source_files`, `baseline`, `forbidden_effects`, `outputs`, `requirements`,
  `iterations`) and an `engine.py` that gathers contracts/sources and runs the checks.
  `verify.py` is now a thin compatibility re-export of `verify_capsule`. No behavior
  change — full test suite (258 tests) and a live `nexu capsule verify` run against the
  `web_app_calculator` example both pass with identical findings/scores.
- Split `cinema_policy.py` (914 lines) into a `cinema_policy/` package of focused submodules
  (`constraints`, `snapshot`, `ledger`, `proposals`, `llm_proposals`, `html_checks`,
  `option_previews`, `intract_validation`, `workspace_verify`). No behavior change — all
  original public and internal names remain importable from `nexu.cinema_policy` via the
  package's `__init__.py`; full test suite (258 tests) passes unchanged.

### Added
- Cinema Intract policy panel: ledger view, manifest apply (`project` / `capsule` / `both`), LLM propose, capsule verify.
- `nexu/cinema_policy.py` and generated `cinema/nexu_hooks.py` for manifest merge, verify, LLM propose, and artifact validation.
- `make cinema-stop`, `make ci-cinema-smoke`, and `scripts/ci-cinema-smoke.sh`.

### Refactor
- Refactor `verify_capsule` into focused checker helpers while preserving report format and scoring behavior.
- Move Cinema manifest/verify/Intract helpers out of embedded `server.py` into `cinema_policy` + `nexu_hooks`.
- Unify MCP tool registration into a single source of truth (`TOOL_SPECS`) and derive `MCP_TOOLS`/dispatch map from it.
- Refactor JSON-RPC routing in `mcp_server` to method-handler mapping for cleaner control flow.
- Refactor CLI path/YAML output duplication via shared helpers.
- Use package `__version__` in MCP `serverInfo` to avoid version drift.

### Fix
- Cinema project switch: reset policy ledger, seed goal/options from active project (`backend_service`, dashboards), distinct A–C from stages; KPI/dashboard spatial DELETE; policy panel shows `active_example_project`.
- `sync_cinema_templates` on each Cinema server start so `cinema_player.html` and `nexu_hooks.py` stay aligned with package templates.
- Respect `llm.allow_network_calls` in `cinema` iteration flow to prevent unintended LLM network calls in offline mode.
- Read API key env and model defaults for `cinema` from `nexu.yaml` (`llm.api_key_env`, `llm.model`) and workspace `.env` (`LLM_MODEL`) instead of hardcoded values.
- Treat intract manifest-only `fail` as warn in `verify_capsule` (capsule code may lag manifest intent).
- Safe LLM empty-content handling in Cinema server; preserve UI annotations when iteration is skipped.

### Test
- `tests/test_cinema_policy.py`, `tests/test_export_prompt_ledger.py`, `tests/test_verify_intract.py`; `tests/conftest.py` adds sibling intract.
- Full suite: `pytest -q` (16 passed); `make ci-cinema-smoke`.

## [0.5.47] - 2026-07-05

### Docs
- Update CHANGELOG.md
- Update README.md

## [0.5.46] - 2026-07-05

### Docs
- Update CHANGELOG.md
- Update README.md

### Other
- Update src/nexu/templates/cinema/server.py.tmpl

## [0.5.45] - 2026-07-05

### Docs
- Update CHANGELOG.md
- Update README.md

## [0.5.44] - 2026-07-05

### Docs
- Update CHANGELOG.md
- Update README.md

## [0.5.43] - 2026-07-05

### Docs
- Update CHANGELOG.md
- Update README.md

### Other
- Update uv.lock

## [0.5.42] - 2026-07-05

### Docs
- Update CHANGELOG.md
- Update README.md

## [0.5.41] - 2026-07-05

### Docs
- Update CHANGELOG.md
- Update README.md

### Other
- Update examples/mcp_patch_demo/local.dev.txt
- Update local.dev.txt

## [0.5.40] - 2026-06-29

### Docs
- Update README.md

### Other
- Update project/planfile-tickets.yaml
- Update uv.lock

## [0.5.39] - 2026-06-29

### Docs
- Update README.md

### Other
- Update uv.lock

## [0.5.38] - 2026-06-29

### Docs
- Update README.md

## [0.5.37] - 2026-06-03

### Docs
- Update SUMD.md
- Update SUMR.md
- Update project/README.md
- Update project/context.md

### Other
- Update app.doql.less
- Update examples/calculator_demo/scientific_calculator_demo.py
- Update examples/calculator_demo/scientific_calculator_demo2.py
- Update examples/lane_integration/realtime_lane_nexu_sync.py
- Update examples/markpact_integration/nexu_markpact_exporter.py
- Update examples/runner/run_examples.py
- Update examples/web_app_calculator/cinema/server.py
- Update project/analysis.toon.yaml
- Update project/calls.mmd
- Update project/calls.toon.yaml
- ... and 14 more files

## [0.5.36] - 2026-06-02

### Docs
- Update SUMR.md

### Other
- Update examples/web_app_calculator/cinema/server.py
- Update project/logic.pl
- Update project/map.toon.yaml
- Update project/planfile-tickets.yaml

## [0.5.35] - 2026-06-02

### Docs
- Update SUMD.md
- Update SUMR.md
- Update project/README.md
- Update project/context.md

### Other
- Update app.doql.less
- Update examples/web_app_calculator/cinema/server.py
- Update project/analysis.toon.yaml
- Update project/calls.mmd
- Update project/calls.png
- Update project/calls.toon.yaml
- Update project/calls.yaml
- Update project/compact_flow.mmd
- Update project/compact_flow.png
- Update project/duplication.toon.yaml
- ... and 10 more files

## [0.5.34] - 2026-06-01

### Docs
- Update docs/cinema-optimizations.md

### Other
- Update Makefile
- Update examples/web_app_calculator/cinema/cinema_player.html
- Update examples/web_app_calculator/cinema/nexu_hooks.py
- Update examples/web_app_calculator/cinema/server.py
- Update uv.lock

## [0.5.33] - 2026-06-01

### Docs
- Update README.md
- Update SUMD.md
- Update SUMR.md
- Update project/README.md
- Update project/context.md

### Other
- Update app.doql.less
- Update project/analysis.toon.yaml
- Update project/calls.mmd
- Update project/calls.png
- Update project/calls.toon.yaml
- Update project/calls.yaml
- Update project/compact_flow.mmd
- Update project/compact_flow.png
- Update project/duplication.toon.yaml
- Update project/evolution.toon.yaml
- ... and 10 more files

## [0.5.32] - 2026-06-01

### Docs
- Update README.md
- Update SUMD.md
- Update SUMR.md
- Update docs/cinema-limitations-and-improvements.md
- Update docs/cinema-optimizations.md
- Update project/README.md

### Test
- Update tests/test_cinema_http_preprocess.py
- Update tests/test_cinema_project_imports.py
- Update tests/test_cinema_server.py

### Other
- Update .dockerignore
- Update app.doql.less
- Update deploy/docker/Dockerfile
- Update deploy/docker/cinema_serve.py
- Update examples/web_app_analytics/cinema/cinema_player.html
- Update examples/web_app_calculator/cinema/cinema_player.html
- Update examples/web_app_dashboard/cinema/cinema_player.html
- Update project/calls.png
- Update project/compact_flow.png
- Update project/duplication.toon.yaml
- ... and 10 more files

## [0.5.31] - 2026-06-01

### Docs
- Update README.md
- Update docs/cinema-limitations-and-improvements.md
- Update docs/cinema-optimizations.md
- Update project/context.md

### Test
- Update tests/test_cinema_project_imports.py
- Update tests/test_cinema_scope.py

### Other
- Update project/analysis.toon.yaml
- Update project/calls.mmd
- Update project/calls.toon.yaml
- Update project/calls.yaml
- Update project/compact_flow.mmd
- Update project/evolution.toon.yaml
- Update project/flow.mmd
- Update project/map.toon.yaml
- Update project/mermaid.export
- Update project/planfile-tickets.yaml
- ... and 1 more files

## [0.5.30] - 2026-06-01

### Docs
- Update README.md
- Update SUMD.md
- Update SUMR.md
- Update docs/cinema-limitations-and-improvements.md

### Test
- Update tests/test_cinema_http_preprocess.py
- Update tests/test_cinema_project_imports.py
- Update tests/test_cinema_scripts.py
- Update tests/test_cinema_server.py

### Other
- Update app.doql.less
- Update project/calls.png
- Update project/duplication.toon.yaml
- Update project/index.html
- Update project/logic.pl
- Update project/map.toon.yaml
- Update project/planfile-tickets.yaml
- Update project/project.toon.yaml
- Update src/nexu/templates/cinema/cinema_player.html.tmpl
- Update uv.lock

## [0.5.29] - 2026-06-01

### Docs
- Update README.md
- Update SUMD.md
- Update SUMR.md
- Update project/README.md
- Update project/context.md

### Test
- Update tests/test_cinema_dom_patch.py
- Update tests/test_cinema_html_validate.py
- Update tests/test_cinema_http_preprocess.py
- Update tests/test_cinema_policy.py
- Update tests/test_cinema_scope.py

### Other
- Update app.doql.less
- Update project/analysis.toon.yaml
- Update project/calls.mmd
- Update project/calls.png
- Update project/calls.toon.yaml
- Update project/calls.yaml
- Update project/compact_flow.mmd
- Update project/compact_flow.png
- Update project/duplication.toon.yaml
- Update project/evolution.toon.yaml
- ... and 11 more files

## [0.5.28] - 2026-06-01

### Docs
- Update README.md
- Update docs/cinema-limitations-and-improvements.md

### Test
- Update tests/test_cinema_marked_context.py
- Update tests/test_cinema_policy.py
- Update tests/test_cinema_scope.py
- Update tests/test_cinema_server.py

### Other
- Update examples/web_app_calculator/cinema/cinema_player.html
- Update examples/web_app_calculator/cinema/nexu_hooks.py
- Update examples/web_app_calculator/cinema/server.py
- Update src/nexu/templates/cinema/cinema_player.html.tmpl
- Update src/nexu/templates/cinema/nexu_hooks.py.tmpl
- Update src/nexu/templates/cinema/server.py.tmpl
- Update uv.lock

## [0.5.27] - 2026-06-01

### Docs
- Update README.md
- Update docs/README.md
- Update docs/cinema-limitations-and-improvements.md
- Update docs/cinema-optimizations.md

### Test
- Update tests/test_cinema_policy.py
- Update tests/test_cinema_server.py

### Other
- Update src/nexu/templates/cinema/cinema_player.html.tmpl
- Update src/nexu/templates/cinema/server.py.tmpl
- Update uv.lock

## [0.5.26] - 2026-06-01

### Docs
- Update README.md
- Update docs/cinema-optimizations.md

### Test
- Update tests/test_cinema_project_imports.py

### Other
- Update examples/web_app_calculator/cinema/server.py
- Update project/planfile-tickets.yaml
- Update src/nexu/templates/cinema/nexu_hooks.py.tmpl
- Update uv.lock

## [0.5.25] - 2026-06-01

### Docs
- Update README.md
- Update SUMD.md
- Update SUMR.md
- Update examples/mcp_patch_demo/README.md
- Update project/README.md
- Update project/context.md

### Test
- Update tests/test_cinema_marked_context.py
- Update tests/test_cinema_policy.py
- Update tests/test_cinema_project_imports.py
- Update tests/test_cinema_project_ir.py
- Update tests/test_cinema_scope.py
- Update tests/test_intract.py

### Other
- Update Makefile
- Update app.doql.less
- Update examples/mcp_patch_demo/index.html
- Update examples/mcp_patch_demo/package.json
- Update examples/mcp_patch_demo/server.js
- Update project/analysis.toon.yaml
- Update project/calls.mmd
- Update project/calls.png
- Update project/calls.toon.yaml
- Update project/calls.yaml
- ... and 18 more files

## [0.5.24] - 2026-06-01

### Docs
- Update README.md
- Update SUMD.md
- Update SUMR.md
- Update docs/cinema-optimizations.md
- Update project/context.md

### Test
- Update tests/test_cinema_dom_patch.py
- Update tests/test_cinema_marked_context.py
- Update tests/test_cinema_ui_patch.py

### Other
- Update app.doql.less
- Update project/analysis.toon.yaml
- Update project/calls.mmd
- Update project/calls.png
- Update project/calls.toon.yaml
- Update project/calls.yaml
- Update project/compact_flow.mmd
- Update project/duplication.toon.yaml
- Update project/flow.mmd
- Update project/index.html
- ... and 6 more files

## [0.5.23] - 2026-06-01

### Docs
- Update README.md
- Update SUMD.md
- Update SUMR.md
- Update project/README.md
- Update project/context.md

### Test
- Update tests/test_cinema_marked_context.py
- Update tests/test_cinema_scope.py
- Update tests/test_cinema_ui_patch.py

### Other
- Update app.doql.less
- Update project/analysis.toon.yaml
- Update project/calls.mmd
- Update project/calls.png
- Update project/calls.toon.yaml
- Update project/calls.yaml
- Update project/compact_flow.mmd
- Update project/compact_flow.png
- Update project/duplication.toon.yaml
- Update project/evolution.toon.yaml
- ... and 11 more files

## [0.5.22] - 2026-06-01

### Docs
- Update README.md
- Update SUMD.md
- Update SUMR.md
- Update docs/cinema-optimizations.md
- Update project/README.md
- Update project/context.md

### Test
- Update tests/test_cinema_dom_patch.py
- Update tests/test_cinema_http_preprocess.py
- Update tests/test_cinema_marked_context.py
- Update tests/test_cinema_project_imports.py
- Update tests/test_cinema_project_ir.py
- Update tests/test_cinema_projects.py
- Update tests/test_cinema_scripts.py
- Update tests/test_cinema_server.py
- Update tests/test_cinema_ui_patch.py

### Other
- Update Makefile
- Update app.doql.less
- Update project/analysis.toon.yaml
- Update project/calls.mmd
- Update project/calls.png
- Update project/calls.toon.yaml
- Update project/calls.yaml
- Update project/compact_flow.mmd
- Update project/compact_flow.png
- Update project/duplication.toon.yaml
- ... and 13 more files

## [0.5.21] - 2026-06-01

### Docs
- Update README.md
- Update SUMD.md
- Update SUMR.md
- Update docs/cinema-optimizations.md
- Update project/README.md
- Update project/context.md

### Test
- Update tests/test_cinema_html_validate.py
- Update tests/test_cinema_http_preprocess.py
- Update tests/test_cinema_iterate.py
- Update tests/test_cinema_llm.py
- Update tests/test_cinema_options_cache.py
- Update tests/test_cinema_project_imports.py
- Update tests/test_cinema_projects.py
- Update tests/test_cinema_scope.py
- Update tests/test_cinema_server.py
- Update tests/test_cinema_traces.py
- ... and 2 more files

### Other
- Update Makefile
- Update app.doql.less
- Update examples/web_app_calculator/cinema/cinema_player.html
- Update examples/web_app_calculator/cinema/nexu_hooks.py
- Update examples/web_app_calculator/cinema/server.py
- Update examples/web_app_calculator/workspace/nexu.yaml
- Update project/analysis.toon.yaml
- Update project/calls.mmd
- Update project/calls.png
- Update project/calls.toon.yaml
- ... and 18 more files

## [0.5.20] - 2026-05-31

### Docs
- Update README.md
- Update docs/examples.md
- Update examples/web_app_calculator/README.md
- Update examples/web_app_dashboard/README.md

### Test
- Update tests/test_cinema_llm.py
- Update tests/test_cinema_server.py
- Update tests/test_cinema_traces.py

### Other
- Update examples/web_app_calculator/workspace/nexu.yaml
- Update examples/web_app_dashboard/workspace/nexu.yaml
- Update scripts/ci-cinema-smoke.sh
- Update src/nexu/templates/cinema/cinema_player.html.tmpl
- Update src/nexu/templates/cinema/server.py.tmpl

## [0.5.19] - 2026-05-31

### Docs
- Update CHANGELOG.md
- Update README.md
- Update docs/llm-orchestration.md
- Update docs/llm-review.md

### Test
- Update tests/test_cinema_goal_contracts.py
- Update tests/test_cinema_llm.py
- Update tests/test_cinema_llm_contracts.py
- Update tests/test_cinema_offline_options.py
- Update tests/test_cinema_project_imports.py
- Update tests/test_cinema_projects.py
- Update tests/test_cinema_scope.py
- Update tests/test_cinema_scripts.py
- Update tests/test_cinema_server.py
- Update tests/test_cinema_spatial_patch.py

### Other
- Update Makefile
- Update examples/web_app_analytics/cinema/stage0.html
- Update examples/web_app_analytics/cinema/stage1.html
- Update examples/web_app_analytics/cinema/stage2.html
- Update examples/web_app_calculator/cinema/cinema_player.html
- Update examples/web_app_calculator/cinema/nexu_hooks.py
- Update examples/web_app_calculator/workspace/nexu.yaml
- Update examples/web_app_dashboard/cinema/stage0.html
- Update examples/web_app_dashboard/cinema/stage1.html
- Update examples/web_app_dashboard/cinema/stage2.html
- ... and 7 more files

## [0.5.18] - 2026-05-31

### Docs
- Update README.md
- Update SUMD.md
- Update SUMR.md
- Update project/README.md
- Update project/context.md

### Test
- Update tests/test_cinema_baseline_contracts.py
- Update tests/test_cinema_markpact.py
- Update tests/test_cinema_offline_options.py
- Update tests/test_cinema_publish.py

### Other
- Update Makefile
- Update app.doql.less
- Update examples/web_app_calculator/cinema/alt_a.html
- Update examples/web_app_calculator/cinema/alt_b.html
- Update examples/web_app_calculator/cinema/alt_c.html
- Update examples/web_app_calculator/cinema/cinema_player.html
- Update examples/web_app_calculator/cinema/stage1.html
- Update examples/web_app_calculator/cinema/stage2.html
- Update project/analysis.toon.yaml
- Update project/calls.mmd
- ... and 21 more files

## [0.5.17] - 2026-05-31

### Docs
- Update README.md

### Test
- Update tests/test_cinema_offline_options.py
- Update tests/test_cinema_server.py

### Other
- Update Makefile
- Update examples/web_app_calculator/cinema/_inject_runtime.html
- Update examples/web_app_calculator/cinema/_inject_shield.html
- Update examples/web_app_calculator/cinema/cinema_player.html
- Update examples/web_app_calculator/cinema/stage0.html
- Update examples/web_app_calculator/cinema/stage1.html
- Update examples/web_app_calculator/cinema/stage2.html
- Update pyqual.yaml
- Update src/nexu/templates/cinema/cinema_player.html.tmpl
- Update src/nexu/templates/cinema/nexu_hooks.py.tmpl
- ... and 1 more files

## [0.5.16] - 2026-05-31

### Docs
- Update CHANGELOG.md
- Update README.md
- Update SUMD.md
- Update SUMR.md
- Update project/context.md

### Test
- Update tests/test_cinema_scripts.py
- Update tests/test_cinema_server.py

### Other
- Update LICENSE
- Update project/analysis.toon.yaml
- Update project/calls.mmd
- Update project/calls.toon.yaml
- Update project/calls.yaml
- Update project/compact_flow.mmd
- Update project/flow.mmd
- Update project/index.html
- Update project/logic.pl
- Update project/mermaid.export
- ... and 2 more files

## [0.5.15] - 2026-05-31

### Docs
- Update README.md

## [0.5.14] - 2026-05-31

### Docs
- Update README.md
- Update SUMD.md
- Update SUMR.md
- Update docs/architecture.md
- Update docs/examples.md
- Update docs/mcp-service.md
- Update docs/roadmap.md
- Update docs/verification.md
- Update examples/backend_service/.tmp_nexu_run/.nexu/capsules/demo/iterations/S1/prompt.md
- Update examples/backend_service/.tmp_nexu_run/.nexu/capsules/demo/iterations/S2/prompt.md
- ... and 38 more files

### Test
- Update tests/test_cinema_markpact.py
- Update tests/test_cinema_policy.py
- Update tests/test_cinema_projects.py
- Update tests/test_cinema_publish.py
- Update tests/test_cinema_server.py

### Other
- Update Makefile
- Update app.doql.less
- Update examples/backend_service/.tmp_nexu_run/.nexu/capsules/demo/blueprints/blueprint.yaml
- Update examples/backend_service/.tmp_nexu_run/.nexu/capsules/demo/bundles/bundle.yaml
- Update examples/backend_service/.tmp_nexu_run/.nexu/capsules/demo/bundles/demo-review-bundle.zip
- Update examples/backend_service/.tmp_nexu_run/.nexu/capsules/demo/capsule.yaml
- Update examples/backend_service/.tmp_nexu_run/.nexu/capsules/demo/evidence/diff.yaml
- Update examples/backend_service/.tmp_nexu_run/.nexu/capsules/demo/evidence/source-drift.yaml
- Update examples/backend_service/.tmp_nexu_run/.nexu/capsules/demo/evidence/verification.yaml
- Update examples/backend_service/.tmp_nexu_run/.nexu/capsules/demo/intract.yaml
- ... and 134 more files

## [0.5.13] - 2026-05-31

### Docs
- Update README.md

### Other
- Update Makefile

## [0.5.12] - 2026-05-31

### Docs
- Update README.md
- Update docs/examples.md
- Update examples/web_app_calculator/README.md
- Update examples/web_app_dashboard/README.md

## [0.5.11] - 2026-05-31

### Docs
- Update README.md

## [0.5.10] - 2026-05-31

### Docs
- Update CHANGELOG.md
- Update README.md
- Update examples/web_app_calculator/README.md

### Test
- Update tests/conftest.py
- Update tests/test_cinema_history.py
- Update tests/test_cinema_policy.py
- Update tests/test_cinema_scripts.py
- Update tests/test_cinema_spatial_patch.py
- Update tests/test_export_prompt_ledger.py
- Update tests/test_verify_intract.py

### Other
- Update Makefile
- Update examples/web_app_calculator/workspace/intract.yaml
- Update scripts/ci-cinema-smoke.sh
- Update uv.lock

## [0.5.9] - 2026-05-31

### Docs
- Update CHANGELOG.md
- Update README.md

### Other
- Update Makefile

## [0.5.8] - 2026-05-31

### Docs
- Update README.md

## [0.5.7] - 2026-05-31

### Docs
- Update README.md
- Update examples/web_app_event_monitor/docker/README.md

### Other
- Update examples/web_app_calculator/workspace/nexu.yaml
- Update examples/web_app_event_monitor/docker/Dockerfile
- Update examples/web_app_event_monitor/docker/docker-compose.yml

## [0.5.6] - 2026-05-31

### Docs
- Update README.md
- Update examples/web_app_calculator/markpact_sandbox/README.md
- Update examples/web_app_event_monitor/services/alerts/README.md
- Update examples/web_app_event_monitor/services/analytics/README.md
- Update examples/web_app_event_monitor/services/dashboard/README.md
- Update examples/web_app_pactown_ecosystem/services/api/README.md
- Update examples/web_app_pactown_ecosystem/services/web/README.md

### Other
- Update .gitignore
- Update examples/nexu_markpact_exporter.py
- Update examples/web_app_calculator/markpact_sandbox/sandbox/requirements.txt
- Update examples/web_app_calculator/markpact_sandbox/sandbox/src/calculator.py
- Update examples/web_app_event_monitor/pactown.yaml
- Update examples/web_app_event_monitor/run.py
- Update examples/web_app_pactown_ecosystem/pactown.yaml
- Update examples/web_app_pactown_ecosystem/run.py

## [0.5.5] - 2026-05-31

### Docs
- Update README.md
- Update TODO/1.md
- Update docs/examples.md
- Update examples/web_app_calculator/README.md
- Update examples/web_app_dashboard/README.md

### Test
- Update tests/test_promote_apply.py

### Other
- Update .env
- Update .gitignore
- Update examples/realtime_lane_nexu_sync.py
- Update examples/scientific_calculator_demo2.py
- Update examples/web_app_analytics/cinema/cinema_player.html
- Update examples/web_app_analytics/cinema/stage0.html
- Update examples/web_app_analytics/cinema/stage1.html
- Update examples/web_app_analytics/cinema/stage2.html
- Update examples/web_app_calculator/cinema/cinema_player.html
- Update examples/web_app_calculator/cinema/stage0.html
- ... and 20 more files

## [0.5.4] - 2026-05-30

### Docs
- Update CHANGELOG.md
- Update README.md

### Other
- Update .gitignore
- Update examples/scientific_calculator_demo.py

## [0.5.3] - 2026-05-30

### Docs
- Update README.md
- Update SUMD.md
- Update SUMR.md
- Update project/README.md
- Update project/context.md

### Other
- Update .gitignore
- Update app.doql.less
- Update project/analysis.toon.yaml
- Update project/calls.mmd
- Update project/calls.png
- Update project/calls.toon.yaml
- Update project/calls.yaml
- Update project/compact_flow.mmd
- Update project/compact_flow.png
- Update project/duplication.toon.yaml
- ... and 10 more files

## [0.5.2] - 2026-05-30

### Docs
- Update README.md
- Update docs/README.md
- Update docs/architecture.md
- Update docs/capsule-format.md
- Update docs/commands.md
- Update docs/examples.md
- Update docs/getting-started.md
- Update docs/intent-contracts.md
- Update docs/llm-orchestration.md
- Update docs/llm-review.md
- ... and 42 more files

### Test
- Update tests/test_capsule_next_stage.py
- Update tests/test_capsule_runtime_report.py
- Update tests/test_orchestration_mcp.py

### Other
- Update examples/backend_service/.tmp_nexu_run/.nexu/capsules/demo/blueprints/blueprint.yaml
- Update examples/backend_service/.tmp_nexu_run/.nexu/capsules/demo/bundles/bundle.yaml
- Update examples/backend_service/.tmp_nexu_run/.nexu/capsules/demo/bundles/demo-review-bundle.zip
- Update examples/backend_service/.tmp_nexu_run/.nexu/capsules/demo/capsule.yaml
- Update examples/backend_service/.tmp_nexu_run/.nexu/capsules/demo/evidence/diff.yaml
- Update examples/backend_service/.tmp_nexu_run/.nexu/capsules/demo/evidence/source-drift.yaml
- Update examples/backend_service/.tmp_nexu_run/.nexu/capsules/demo/evidence/verification.yaml
- Update examples/backend_service/.tmp_nexu_run/.nexu/capsules/demo/intract.yaml
- Update examples/backend_service/.tmp_nexu_run/.nexu/capsules/demo/iterations/S0/state.yaml
- Update examples/backend_service/.tmp_nexu_run/.nexu/capsules/demo/iterations/S1/state.yaml
- ... and 101 more files

## [0.5.1] - 2026-05-30

### Docs
- Update CHANGELOG.md
- Update README.md
- Update docs/README.md
- Update docs/architecture.md
- Update docs/capsule-format.md
- Update docs/commands.md
- Update docs/examples.md
- Update docs/getting-started.md
- Update docs/llm-orchestration.md
- Update docs/llm-review.md
- ... and 4 more files

### Test
- Update tests/test_capsule_runtime_report.py
- Update tests/test_orchestration_mcp.py
- Update tests/test_review_bundle.py

### Other
- Update VERSION
- Update examples/mcp_service/src/demo.py
- Update examples/run_examples.py
- Update uv.lock


## 0.5.0

- Added `nexu capsule orchestrate` for offline or optional LLM-assisted capsule orchestration.
- Added `src/nexu/orchestrate.py` with orchestration context, prompt, deterministic plan and markdown output.
- Added generic LiteLLM JSON helper for orchestration/review while keeping network calls disabled by default.
- Added conservative MCP-compatible stdio service with tools, resources and prompt templates.
- Added `nexu mcp tools` and `nexu mcp serve`.
- Added MCP service example and documentation.

## 0.4.0

- Added offline/optional LLM review packets with strict JSON review schema.
- Added `nexu capsule review` to generate evidence-based review prompts and review YAML/Markdown.
- Added `nexu capsule bundle` for portable ZIP bundles of capsule context, prompts and evidence.
- Added `nexu.config` and LLM/review settings in `nexu.yaml`.
- Strengthened promotion plans with prechecks, drift status, blocking findings and file mapping.

## 0.3.0

- Added `nexu capsule plan` for deterministic S1..Sn iteration planning.
- Added `nexu capsule runtime` to build a static HTML mock/runtime from capsule blueprint, contracts and fixtures.
- Added `nexu capsule report` with Markdown, HTML and YAML verification evidence.
- Added `nexu capsule journal` for capsule event history.
- Added journal hooks for capsule creation, planning, runtime and reports.
- Updated examples and docs for the runtime/report workflow.

## 0.2.0

- Added capsule status, blueprint, prompt export, diff and source drift checks.
- Added richer verification for baseline lock, forbidden writes, secret-like values, outputs and required intents.

## 0.1.0

- Initial freeze → capsule → iterate → verify → promote MVP.
