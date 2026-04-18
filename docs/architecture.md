# Architecture

El Sbobinator is a Windows/macOS desktop application that turns audio lectures into structured Italian study notes. The backend is a Python pipeline that talks to the Google Gemini API; the frontend is a React/TypeScript SPA hosted inside a [pywebview](https://pywebview.flowrl.com/) window. There is no server component — everything runs locally, and API calls go directly from the user's machine to Google.

## Repository layout

| Path | What it contains |
|---|---|
| `el_sbobinator/` | Python package: pipeline, Gemini integration, pywebview backend, configuration, FFmpeg wrappers |
| `webui/` | React + TypeScript frontend (Vite, Tailwind, TipTap, dnd-kit) |
| `launchers/` | PyInstaller entrypoint (`El_Sbobinator_WebUI.pyw`) |
| `packaging/` | Inno Setup script (Windows), `create-dmg` wrapper (macOS), double-click build scripts |
| `scripts/` | `build_release.py` (single source of truth for deps/check/build), `smoke_test.py` |
| `requirements/` | Pinned (`requirements.lock`), runtime (`requirements.txt`), dev (`requirements-dev.txt`) |
| `tests/` | `unittest` suite for the Python package |
| `tools/` | Dev utilities (e.g. `profile_imports.py`) |
| `docs/` | Developer documentation (this file, `pipeline.md`, `session_model.md`, `bridge_protocol.md`) |
| `.github/` | Issue/PR templates, GitHub Actions build workflow |
| `assets/` | Platform icons (`.ico`, `.icns`) |

## Python module map (`el_sbobinator/`)

| Module | Responsibility | Key symbols |
|---|---|---|
| `app_webview.py` | pywebview entrypoint, JS API, `PipelineAdapter`, `_BridgeDispatcher`, WebView2 runtime detection, cache-bust on update | `main`, `ElSbobinatorApi`, `PipelineAdapter`, `_BridgeDispatcher` |
| `app.py` | Legacy compatibility shim — delegates to `app_webview.main` | `main`, `ElSbobinatorApp` |
| `bridge_types.py` | `TypedDict` payload shapes shared with the frontend (`WorkTotalsPayload`, `FileDonePayload`, `ValidationResult`, …) | — |
| `pipeline.py` | Pipeline orchestrator — probes duration, runs phases 1/2/3, exports HTML | `esegui_sbobinatura`, `_esegui_sbobinatura_impl` |
| `pipeline_hooks.py` | Duck-typed indirection between pipeline code and whatever UI is attached | `PipelineRuntime` |
| `pipeline_session.py` | Bootstrap/resume: session init, stage normalization, phase-1 progress restore, pre-conversion, step-time metrics | `initialize_session_context`, `PipelineSessionContext`, `restore_phase1_progress`, `ensure_preconverted_audio`, `record_step_metric` |
| `pipeline_settings.py` | Loading + clamping settings from `session.json` (per-model defaults, legacy `macro_char_limit` migration) | `PipelineSettings`, `load_and_sanitize_settings`, `build_default_pipeline_settings` |
| `phase1_service.py` | Phase 1: chunked transcription loop with FFmpeg prefetch + chain-exhaustion recovery | `process_phase1_transcription` |
| `revision_service.py` | Phase 2 (macro revision with two-pass retry via `.raw.md`) and phase 3 (boundary AI fallback) | `build_macro_blocks`, `process_macro_revision_phase`, `process_boundary_revision_phase` |
| `generation_service.py` | Gemini transport: `retry_with_quota`, key rotation, model fallback, degenerate-output guardrail | `retry_with_quota`, `try_rotate_key`, `DegenerateOutputError`, `QuotaDailyLimitError`, `AllModelsUnavailableError`, `PermanentError`, `detect_degenerate_output`, `_phase1_temperature` |
| `model_registry.py` | Supported Gemini models, per-model defaults (`default_chunk_minutes`, `default_macro_char_limit`, `phase1_temperature`), fallback-chain helpers | `MODEL_OPTIONS`, `ModelState`, `build_model_state`, `next_model_in_chain`, `sanitize_model_name`, `sanitize_fallback_models` |
| `prompts.py` | The three Gemini prompts (`PROMPT_SISTEMA`, `PROMPT_REVISIONE`, `PROMPT_REVISIONE_CONFINE`) | — |
| `session_store.py` | On-disk session layout: `SessionPaths`, `new_session`, `load_session`, `save_session`, `resolve_session_paths`, `reset_session_dirs` | — |
| `shared.py` | Fingerprint-based session IDs, `SESSION_ROOT`, atomic-write helpers, orphan-session cleanup, session-storage info cache | `_session_id_for_file`, `_session_dir_for_file`, `_atomic_write_json`, `_atomic_write_text`, `cleanup_orphan_sessions`, `get_session_storage_info` |
| `config_service.py` | OS-aware config file paths, DPAPI (Windows) and keyring (macOS/Linux) helpers, desktop path resolution, filename sanitization | `load_config`, `save_config`, `get_desktop_dir`, `safe_output_basename` |
| `validation_service.py` | Environment checks used by the WebUI "Validate environment" action and by the release smoke test | `validate_environment` |
| `audio_service.py` | Thin facade over `ffmpeg_utils` (`resolve_ffmpeg`, `probe_media_duration`, `preconvert_media_to_mp3`, `cut_audio_chunk_to_mp3`) | — |
| `ffmpeg_utils.py` | FFmpeg subprocess helpers: cancellable runner, duration probe, mono-16 kHz MP3 pre-conversion, chunk cut (stream-copy or reencode) | `get_ffmpeg_exe`, `probe_duration_seconds`, `preconvert_to_mono16k_mp3`, `cut_chunk_to_mp3` |
| `dedup_utils.py` | Conservative pre-AI cleanup for macro blocks (exact + near-adjacent duplicates) | `local_macro_cleanup` |
| `export_service.py` | Final assembly: load `rev_NNN.md` files, build title + markdown, write final HTML | `export_final_html_document`, `load_revised_blocks`, `resolve_output_html_path` |
| `html_export.py` | Markdown → HTML with `markdown` + `nh3` sanitizer, list/heading normalization, CSP-locked document template | `build_html_document`, `sanitize_html_basic`, `normalize_inline_star_lists`, `normalize_heading_levels` |
| `file_ops.py` | FS helpers used by the pywebview bridge: `open_path_with_default_app`, HTML body save with generation-counter concurrency guard, `.docx` export via `html2docx` | `open_path_with_default_app`, `read_html_content`, `save_html_body_content`, `extract_html_shell`, `export_doc_html` |
| `media_server.py` | Tiny local HTTP server with Range support so the React audio player can stream session audio | `LocalMediaServer` |
| `logging_utils.py` | Structured logger with session-scoped context (`run_id`, `session_dir`, `stage`, `input_file`) + per-session file handler | `get_logger`, `configure_logging`, `attach_file_handler`, `detach_file_handler` |
| `updater.py` | Auto-update: downloads the OS-specific release asset from GitHub and launches it (Windows installer / macOS DMG) | `download_and_install_update` |

## Frontend module map (`webui/src/`)

| Path | Responsibility |
|---|---|
| `main.tsx` | React entrypoint + `RootErrorBoundary` |
| `App.tsx` | Top-level app shell: queue, drag-and-drop, processing banner, modal wiring, confetti |
| `appState.ts` | `processingReducer` + `ProcessingState`/`ProcessingAction` types (single source of truth for queue + progress state) |
| `bridge.ts` | `PywebviewApi` interface (JS → Python) and `BridgeCallbacks` (Python → JS) with `createBridge` factory |
| `RichTextEditor.tsx` | TipTap editor with TOC, search-highlight, find-and-replace, font-size, word-count |
| `AudioPlayer.tsx` | Editor audio player: waveform-free controls, bookmarking, persistent time/volume |
| `FloatingImage.tsx` | Resize/align/layout affordances for editor-embedded images |
| `previewHtml.ts` | Normalize preview HTML before loading into the editor |
| `editorSessions.ts` | Per-file editor-session persistence (scroll, audio position) via `localStorage` |
| `duplicateDetection.ts` | Archive-lookup helpers used by the "already processed" modal |
| `branding.ts` | Constants for GitHub/Ko-fi/releases URLs |
| `utils.ts` | `errorLabel` mapping (Python `last_error` → Italian UI string), formatters |
| `index.css` | Tailwind v4 base + custom rules (including editor + TOC) |
| `components/ProcessingStatusBanner.tsx` | Top-of-screen banner while a batch is running (ETA, phase, model badge) |
| `components/QueueFileCard.tsx` | Queue item card (pending + completed variants) |
| `components/modals/*.tsx` | `SettingsModal`, `PreviewModal`, `RegenerateModal`, `NewKeyModal`, `DuplicateFileModal`, `ConfirmActionModal` |
| `hooks/useApiReady.ts` | Polls `window.pywebview.api` until ready, then binds the bridge |
| `hooks/useBridgeCallbacks.ts` | Wires `BridgeCallbacks` onto `window.elSbobinatorBridge` |
| `hooks/useQueuePersistence.ts` | Persists the file queue across app restarts |
| `hooks/useConsole.ts` | Captures `appendConsole` messages for the in-app terminal |
| `hooks/useTheme.ts` | Light/dark theme toggle |
| `hooks/useUpdateChecker.ts` | Polls GitHub releases for update notifications |
| `hooks/useBodyScrollLock.ts` | Scroll-lock when a modal is open |

## Runtime flow

```
packaged exe / python  launchers/El_Sbobinator_WebUI.pyw
         │
         ▼
el_sbobinator.app_webview.main()
         │
         ├─ detect WebView2 runtime (Windows) → fallback HTML if missing
         ├─ create pywebview window  ◄──────  js_api = ElSbobinatorApi
         ├─ spawn LocalMediaServer on demand
         └─ webview.start()
                 │
                 │  user clicks "Avvia"
                 ▼
     ElSbobinatorApi.start_processing(...)
                 │  worker thread (one per batch)
                 ▼
     for each file:
       pipeline.esegui_sbobinatura(...)
           │                                  (duck-typed app_instance
           ▼                                   = PipelineAdapter)
       PipelineRuntime(app_instance)
           │
           ├─► phase1_service.process_phase1_transcription
           │       FFmpeg cut → Gemini generate → autosave chunk_NNN.md
           │
           ├─► revision_service.process_macro_revision_phase
           │       build_macro_blocks → AI revise → rev_NNN.md (+ .raw.md retry pass)
           │
           ├─► revision_service.process_boundary_revision_phase
           │       local similarity gate → AI stitch → boundary_NNN.done
           │
           └─► export_service.export_final_html_document
                   rev_NNN.md → build_html_document → <Title>_Sbobina.html
```

All pipeline → UI updates go through `PipelineRuntime` (`el_sbobinator/pipeline_hooks.py`), which forwards to `PipelineAdapter` methods on the adapter. The adapter buffers them through `_BridgeDispatcher`, which calls `window.evaluate_js("window.elSbobinatorBridge.<event>(<json>)")` roughly every 80 ms. React's `processingReducer` then consumes the events. See [`bridge_protocol.md`](./bridge_protocol.md) for the full event/API tables.

## Threading model

- **UI thread** — owned by pywebview / WebView2. Receives all JS API calls.
- **Pipeline worker** — one background thread per batch (started by `ElSbobinatorApi.start_processing`). Runs `esegui_sbobinatura` sequentially per file.
- **FFmpeg prefetch thread** — inside phase 1, each iteration may spawn a daemon thread that cuts the *next* chunk while the current one is being sent to Gemini (controlled by `PipelineSettings.prefetch_next_chunk`).
- **`_BridgeDispatcher` timer** — single shared `threading.Timer` that flushes queued UI events.
- **`LocalMediaServer` threads** — one `ThreadingTCPServer` per actively streamed audio file (LRU-capped at 5).
- **Session-storage info thread** — one long-lived `ThreadPoolExecutor` worker in `shared.py` that recomputes total session size / count on demand (with a 30 s cache).

## Further reading

- [`pipeline.md`](./pipeline.md) — phase-by-phase walk-through, error classes, `last_error` values, model fallback.
- [`session_model.md`](./session_model.md) — on-disk session layout and `session.json` schema.
- [`bridge_protocol.md`](./bridge_protocol.md) — Python ↔ JS event and API contracts.
