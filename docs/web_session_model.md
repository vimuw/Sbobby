# Web Session & Job Model

This document defines the canonical job identity, lifecycle, storage layout, and
session metadata schema for the web version of El Sbobinator. It is the gating
design decision that constrains the backend storage abstraction, the FastAPI bridge,
and the worker queue implementation.

---

## 1. Identity

**In the desktop app** session identity is derived from a file fingerprint
(`path + size + mtime`), computed in `new_session()` inside `session_store.py`.
"Same file on disk" meant "resume previous session."

**In the web app** identity is job-scoped:

- Every upload creates a new job with a fresh `job_id` (UUID v4, server-assigned).
- `job_id` is the only canonical identity anchor throughout the system.
- File fingerprinting is **not used for resume routing**. It may be computed as a
  separate `content_hash` field for optional deduplication warnings, but it does
  not determine which session a job maps to.
- Resume means "continue job `<job_id>` from its checkpoints," never "detect same
  file and attach to an older session."

### What this retires

| Desktop artifact | Reason retired |
|---|---|
| `_session_dir_for_file()` in `shared.py` | Derived session path from file path; replaced by job-scoped prefix |
| `_session_id_for_file()` in `shared.py` | Fingerprint-based session ID; replaced by `job_id` |
| `resolve_session_paths(input_path)` in `session_store.py` | Input-path-centric path resolution; replaced by `JobPaths(job_id)` |
| `input_path` as identity in `PipelineSessionContext` | Local OS path; replaced by `job_id` + `source_object_key` |
| `resume_session: bool` flag at job start | No user-driven "resume same file"; auto-resume only (see §3) |

---

## 2. Job Lifecycle

```
queued ──► running ──► done
                  └──► failed
```

State transitions:

| From | To | Trigger |
|---|---|---|
| `queued` | `running` | Worker picks up the job |
| `running` | `done` | Pipeline completes successfully |
| `running` | `failed` | Unrecoverable error (API auth, FFmpeg failure, timeout) |
| `running` | `running` | Automatic checkpoint resume after transient failure (rate limit, worker restart) — no state transition, just internal restart from last checkpoint |

**Deferred to V2:** `needs_input` state for in-flight worker pauses (covers the
`ask_regenerate` and `ask_new_api_key` desktop interactions). In V1 these are
handled as follows:

- `ask_new_api_key`: eliminated by validating the API key at job submission. Job is
  rejected before it enters `queued` if the key is absent or structurally invalid.
- `ask_regenerate`: eliminated by making regeneration a pre-job decision at the API
  level, not a mid-flight worker pause.

---

## 3. Resume Contract

Resume is **automatic and checkpoint-based**. It is not user-initiated in V1.

A worker starting or restarting a job with `stage != "done"` reads checkpoints from
cloud storage and continues from the last completed step. This covers:

- Worker process restart
- Gemini rate-limit causing mid-job failure and retry
- Transient network errors during generation

The resume logic in `pipeline_session.py` (`phase1_has_progress`,
`restore_phase1_progress`) is preserved, operating on the cloud-backed checkpoint
prefix instead of a local directory.

---

## 4. Storage Layout

All job artifacts are stored under a single job-scoped prefix:

```
jobs/{job_id}/
  source.{ext}                          # original uploaded file (immutable after upload)
  preconverted.mp3                      # FFmpeg-converted audio (was el_sbobinator_preconverted_mono16k.mp3)
  phase1_chunks/
    chunk_001_0_900.md                  # naming convention unchanged
    chunk_002_870_1800.md
    ...
  phase2_revised/
    chunk_001_0_900.md
    ...
  phase2_boundary/
    boundary_001_002.md
    ...
  phase2_macro_blocks.json              # unchanged format
  session.json                          # session metadata (schema defined in §5)
  output.html                           # final export (written on completion)
```

Object keys map directly to the paths currently used in `SessionPaths`:

| `SessionPaths` field (desktop) | Web object key |
|---|---|
| `session_path` | `jobs/{job_id}/session.json` |
| `phase1_chunks_dir/chunk_*.md` | `jobs/{job_id}/phase1_chunks/chunk_*.md` |
| `phase2_revised_dir/chunk_*.md` | `jobs/{job_id}/phase2_revised/chunk_*.md` |
| `boundary_dir/boundary_*.md` | `jobs/{job_id}/phase2_boundary/boundary_*.md` |
| `macro_path` | `jobs/{job_id}/phase2_macro_blocks.json` |

Chunk file naming (`chunk_XXX_YYYYY_ZZZZZ.md`) is unchanged so that
`list_phase1_chunks()` in `pipeline_session.py` works without modification.

---

## 5. Session Metadata Schema (`session.json`)

The `session.json` structure is preserved from the desktop version with two
changes: the `input` field drops fingerprint data and the top-level `job_id`
field is added.

```json
{
  "schema_version": 3,
  "job_id": "<uuid4>",
  "created_at": "<iso8601>",
  "updated_at": "<iso8601>",
  "stage": "phase1 | phase2 | boundary | done",
  "input": {
    "source_object_key": "jobs/<job_id>/source.<ext>",
    "original_filename": "<user-supplied filename>",
    "size": 123456789,
    "content_hash": "<sha256hex | null>"
  },
  "settings": {
    "model": "gemini-2.5-flash",
    "chunk_minutes": 15,
    "overlap_seconds": 30,
    "macro_char_limit": 22000,
    "preconvert_audio": true,
    "prefetch_next_chunk": true,
    "inline_audio_max_mb": 6.0,
    "audio": {
      "bitrate": "48k"
    }
  },
  "phase1": {
    "next_start_sec": 0,
    "chunks_done": 0,
    "memoria_precedente": "",
    "duration_seconds": null,
    "step_seconds": null,
    "preconverted_done": false
  },
  "phase2": {
    "macro_total": 0,
    "revised_done": 0
  },
  "boundary": {
    "pairs_total": 0,
    "next_pair": 1
  },
  "outputs": {
    "html_object_key": "jobs/<job_id>/output.html | null"
  },
  "metrics": {},
  "last_error": null
}
```

### Changes from desktop schema

| Field | Desktop | Web |
|---|---|---|
| `input.path` | Local absolute OS path | **Removed** |
| `input.mtime` | File modification timestamp | **Removed** |
| `input.source_object_key` | *(absent)* | Cloud storage object key for the uploaded file |
| `input.original_filename` | *(absent)* | User-visible filename from upload |
| `input.content_hash` | *(absent)* | SHA-256 of uploaded file; **non-identity**, deduplication only |
| `job_id` | *(absent)* | UUID v4, primary identity |
| `outputs.html` | Local file path on Desktop | **Renamed** to `outputs.html_object_key`; value is a cloud storage key |

All other fields (`settings`, `phase1`, `phase2`, `boundary`, `metrics`,
`last_error`) are structurally identical to the desktop schema. `new_session()` in
`session_store.py` will be updated to accept `job_id + source_object_key +
original_filename` instead of `input_path`.

---

## 6. Content Hash: Non-Identity

`content_hash` (SHA-256 of the uploaded file) is stored in `session.json` under
`input.content_hash` and optionally in a separate job registry. It is:

- **Computed once** at upload time (or lazily on first worker start)
- **Stored** per job, not as a global lookup key
- **Used only for** duplicate upload warnings and storage deduplication hints
- **Never used** to route resume, merge sessions, or derive `job_id`

This keeps the hash available for future optimization without letting it become a
hidden identity mechanism.

---

## 7. `PipelineSessionContext` Replacement

The current `PipelineSessionContext` dataclass in `pipeline_session.py` carries
`input_path`, `session_dir_hint`, `resume_session`, and a `SessionPaths` object.
In the web version these are replaced:

```python
@dataclass
class WebPipelineSessionContext:
    job_id: str
    source_object_key: str          # e.g. "jobs/<job_id>/source.mp4"
    session_prefix: str             # e.g. "jobs/<job_id>/"
    storage: StorageBackend         # abstraction over local FS or cloud
    session: dict                   # same dict structure as §5
    settings: PipelineSettings      # unchanged
    settings_changed: bool          # unchanged
```

`StorageBackend` is a minimal interface with `read(key)`, `write(key, data)`,
`exists(key)`, `list_prefix(prefix)`, and `delete(key)`. The local filesystem
implementation wraps the current `_atomic_write_json` / `_load_json` helpers.
The cloud implementation wraps an R2/S3 client. The pipeline never calls either
directly — all I/O routes through `WebPipelineSessionContext` or the storage
interface.

---

## 8. Decisions Locked In

These decisions are fixed for V1 and constrain all subsequent implementation:

1. `job_id` (UUID) is the only identity anchor. File fingerprints are non-identity.
2. Resume is automatic and checkpoint-based. No user-initiated "resume same file."
3. Checkpoints are stored under `jobs/{job_id}/` in cloud storage.
4. `ask_new_api_key` is eliminated via pre-job key validation.
5. `ask_regenerate` is a pre-job decision, not an in-flight worker pause.
6. Job lifecycle is `queued → running → done | failed`. `needs_input` is V2.
7. `session.json` schema is backward-compatible with desktop except for the `input`
   field changes listed in §5.
