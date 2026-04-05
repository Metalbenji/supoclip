# Configuration Reference

This is the single source of truth for MrglSnips runtime environment variables.

## Core Variables

| Variable | Required | Default | Used By | Notes |
|---|---|---|---|---|
| `TRANSCRIPTION_PROVIDER` | No | `local` | backend, worker | Transcription backend: `local` or `assemblyai`. When `assemblyai` is requested but media exceeds AssemblyAI limits (10h duration or local upload >2.2 GiB), backend falls back to `local`. |
| `ASSEMBLY_AI_API_KEY` | Conditional | - | backend, worker | Required when `TRANSCRIPTION_PROVIDER=assemblyai`. |
| `MEDIAPIPE_FACE_MODEL_PATH` | No | `backend/models/blaze_face_short_range.tflite` (local), `/app/models/blaze_face_short_range.tflite` (Docker) | backend, worker | File path for MediaPipe Tasks face detector model used for face-aware crop. |
| `MEDIAPIPE_FACE_MODEL_URL` | No | Google MediaPipe model URL | backend, worker | Download URL used when model file is missing and auto-download is enabled. |
| `MEDIAPIPE_FACE_MODEL_SHA256` | No | `b4578f35940bf5a1a655214a1cce5cab13eba73c1297cd78e1a04c2380b0152f` | backend, worker | Optional integrity check for downloaded/baked face model file. |
| `MEDIAPIPE_FACE_MODEL_AUTO_DOWNLOAD` | No | `true` | backend, worker | Auto-download face model if missing at startup/runtime. |
| `LLM` | No | `openai:gpt-5-mini` | backend, worker | Primary model selector (`provider:model`). |
| `MAX_CLIPS` | No | `10` | backend, worker | Maximum number of AI-selected clip segments returned after validation/diversity filtering. |
| `CLIP_DIVERSITY_ENABLED` | No | `true` | backend, worker | Enable timeline diversity filtering after AI scoring. |
| `CLIP_DIVERSITY_MIN_GAP_SECONDS` | No | `600` | backend, worker | Preferred minimum separation between selected clip start times. |
| `CLIP_DIVERSITY_BUCKETS` | No | `4` | backend, worker | Number of timeline coverage buckets used by diversity filtering. |
| `OPENAI_API_KEY` | Conditional | - | backend, worker | Required when `LLM` uses `openai:*`. |
| `GOOGLE_API_KEY` | Conditional | - | backend, worker | Required when `LLM` uses `google:*`. |
| `ANTHROPIC_API_KEY` | Conditional | - | backend, worker | Required when `LLM` uses `anthropic:*`. |
| `ZAI_API_KEY` | Conditional | - | backend, worker | Required when `LLM` uses `zai:*`; requests use z.ai Coding API endpoint (`/api/coding/paas/v4`). |
| `OLLAMA_BASE_URL` | No | `http://localhost:11434` (local) / `http://host.docker.internal:11434` (Docker compose env) | backend, worker | Base URL for Ollama when `LLM` uses `ollama:*` or AI provider is set to `ollama` in Settings. |
| `OLLAMA_TIMEOUT_SECONDS` | No | `15` | backend, worker | Env fallback timeout (seconds) for Ollama model discovery/runtime calls when user-level override is not set. |
| `OLLAMA_MAX_RETRIES` | No | `2` | backend, worker | Env fallback retry count for Ollama HTTP calls when user-level override is not set. |
| `OLLAMA_RETRY_BACKOFF_MS` | No | `400` | backend, worker | Env fallback backoff (milliseconds) for Ollama retries when user-level override is not set. |
| `WHISPER_MODEL_SIZE` | No | `medium` | backend, worker | Whisper size: `tiny`, `base`, `small`, `medium`, `large`, or `turbo`. User Settings can override the local Whisper model per future task. |
| `WHISPER_DEVICE` | No | `auto` | backend, worker | Whisper execution target: `auto`, `cuda`, or `cpu`. |
| `WHISPER_GPU_INDEX` | No | unset | backend, worker | Preferred GPU index for local Whisper when GPU execution is selected; leave unset to use the first visible GPU. |
| `WHISPER_CHUNKING_ENABLED` | No | `true` | backend, worker | Enable chunked local Whisper transcription for long videos. |
| `WHISPER_CHUNK_DURATION_SECONDS` | No | `1200` | backend, worker | Chunk length (seconds) for local Whisper transcription when chunking is enabled. |
| `WHISPER_CHUNK_OVERLAP_SECONDS` | No | `8` | backend, worker | Overlap duration (seconds) between local Whisper chunks to preserve boundary context. |
| `WORKER_MAX_JOBS` | No | `2` | worker | Max concurrent background jobs for primary worker; lower values reduce CPU contention during local transcription. |
| `WORKER_JOB_TIMEOUT_SECONDS` | No | `21600` | worker | ARQ job timeout for a single video task (seconds). Also acts as the maximum allowed per-task timeout selected in the Settings UI. |
| `WORKER2_MAX_JOBS` | No | `1` | worker2 (optional) | Max concurrent jobs for optional second worker (`multi-worker` profile). |
| `WORKER2_WHISPER_DEVICE` | No | `auto` | worker2 (optional) | Whisper target device for second worker: `auto`, `cuda`, `cpu`. |
| `ENABLE_MULTI_WORKER` | No | `false` | start.sh | When true, `./start.sh` runs Docker Compose with profile `multi-worker` to include `worker2`. |
| `WORKER_GPU_WHISPER_DEVICE` | No | `cuda` | worker-gpu (optional) | Whisper target device for optional GPU worker profile. |
| `ENABLE_GPU_WORKER` | No | `false` | start.sh | When true, `./start.sh` runs Docker Compose with profile `gpu-worker` to include `worker-gpu`. |
| `ENABLE_ASSEMBLY_WORKER` | No | `false` | start.sh | When true, `./start.sh` runs Docker Compose with profile `assembly-worker` to include `worker-assembly`. `./start.sh` also enables that profile automatically when `TRANSCRIPTION_PROVIDER=assemblyai`. |
| `ARQ_QUEUE_NAME_LOCAL` | No | `arq:queue:local` | backend, workers | Queue name for local Whisper jobs. |
| `ARQ_QUEUE_NAME_LOCAL_GPU` | No | `arq:queue:local-gpu` | backend, workers | Queue name for local Whisper jobs that should prefer the GPU worker. |
| `ARQ_QUEUE_NAME_ASSEMBLY` | No | `arq:queue:assembly` | backend, workers | Queue name for AssemblyAI jobs. |
| `ADMIN_API_KEY` | No | - | backend | Optional key for admin task-management endpoints (send as `x-admin-key`). |
| `APP_HOST` | No | `localhost` | docs, startup output | Hostname used to build default browser-facing local URLs. |
| `FRONTEND_HOST_PORT` | No | `3000` | docker-compose, startup output | Host port published for frontend container port `3000`. |
| `BACKEND_HOST_PORT` | No | `8000` | docker-compose, startup output | Host port published for backend container port `8000`. |
| `POSTGRES_HOST_PORT` | No | `5433` | docker-compose | Host port published for PostgreSQL container port `5432`. |
| `REDIS_HOST_PORT` | No | `6379` | docker-compose | Host port published for Redis container port `6379`. |
| `BETTER_AUTH_TRUSTED_ORIGINS` | No | `http://localhost:3000,http://127.0.0.1:3000` | frontend | Comma-separated Better Auth origin allowlist for local/dev. |
| `DOCKER_GPU_REQUEST` | No | `all` | docker-compose | GPU device request for backend/worker (`all` or `0`). |
| `DOCKER_GPU_REQUEST_WORKER2` | No | `all` | docker-compose | GPU device request for optional `worker2` profile (`all` or `0`). |
| `DOCKER_GPU_REQUEST_WORKER_GPU` | No | `all` | docker-compose | GPU device request for optional `worker-gpu` profile (`all` or `0`). |
| `DOCKER_GPU_REQUEST_WORKER_ASSEMBLY` | No | `all` | docker-compose | GPU device request for optional `worker-assembly` profile. |
| `SECRET_ENCRYPTION_KEY` | No | - | backend | Optional encryption secret for user-stored API keys (recommended for production). |
| `WHISPER_CACHE_HOST_DIR` | No | `./backend/.cache/whisper` | docker-compose | Host bind-mount location for Whisper model cache (`/root/.cache/whisper` in containers). |
| `TEMP_DIR` | No | `temp` (local) / `/app/uploads` (Docker) | backend, worker | Working directory for uploaded/downloaded files and clip output paths. |
| `YTDLP_COOKIES_FILE` | No | unset | backend, worker | Optional Netscape-format cookies file used by `yt-dlp` for YouTube videos that trigger bot-check/login requirements. In Docker compose, place the file under `backend/.secrets/` and point this var at `/app/.secrets/<file>.txt`. |
| `DATABASE_URL` | Yes | compose-provided value | backend, worker | Postgres connection string. |
| `REDIS_HOST` | Yes (Docker) | `localhost` | backend, worker | Redis host. |
| `REDIS_PORT` | No | `6379` | backend, worker | Redis port. |
| `BETTER_AUTH_SECRET` | Yes for production | dev placeholder | frontend | Must be randomized for production. |
| `POSTGRES_DB` | Yes (Docker setup) | `supoclip` | postgres init | Database name for compose setup. |
| `POSTGRES_USER` | Yes (Docker setup) | `supoclip` | postgres init | Database user for compose setup. |
| `POSTGRES_PASSWORD` | Yes (Docker setup) | `supoclip_password` | postgres init | Database password for compose setup. |

## Local Host Mapping Variables

For local URL/port changes, edit host mapping vars in root `.env` (template: `.env.sample`) and then run `docker compose config` to confirm rendered mappings.

Derived browser URLs:
- Frontend: `http://${APP_HOST}:${FRONTEND_HOST_PORT}`
- Backend: `http://${APP_HOST}:${BACKEND_HOST_PORT}`

Reference quick lookup: `docs/local-host-mappings.md`.

## Backward Compatibility Variables

These are accepted for compatibility with older local setups:

| Legacy Variable | Preferred Variable |
|---|---|
| `LLM_MODEL` | `LLM` |
| `WHISPER_MODEL` | `WHISPER_MODEL_SIZE` |

## Model String Format

Use `provider:model`.

Examples:
- `openai:gpt-5`
- `openai:gpt-5-mini`
- `openai:gpt-4.1`
- `anthropic:claude-4-sonnet`
- `google:gemini-2.5-pro`
- `zai:glm-5`
- `ollama:gpt-oss:latest`

## z.ai Key Routing (UI/DB)

- In Settings, z.ai supports two user-stored key profiles:
  - `subscription`
  - `metered`
- User-level routing mode controls how keys are selected:
  - `auto` (tries subscription, then metered, then legacy/env fallback)
  - `subscription`
  - `metered`
- On z.ai balance/package errors (for example code `1113`), `auto` mode retries with the next profile key.

## Ollama Server Settings (UI/DB)

- AI provider `ollama` supports multiple per-user server profiles (`user_ollama_server_profiles`):
  - `profile_name`, `base_url`, `enabled`, `is_default`
  - auth modes: `none`, `bearer`, `custom_header`
  - auth token is encrypted at rest (`auth_secret_encrypted`)
- User-level defaults:
  - `default_ollama_profile`
  - `default_ollama_timeout_seconds`
  - `default_ollama_max_retries`
  - `default_ollama_retry_backoff_ms`
- Resolution order for model listing/runtime:
  1. request overrides (profile/base URL/timeout-retry controls)
  2. user profile + user request-control defaults
  3. env fallback (`OLLAMA_BASE_URL`, `OLLAMA_TIMEOUT_SECONDS`, `OLLAMA_MAX_RETRIES`, `OLLAMA_RETRY_BACKOFF_MS`)
  4. hard defaults (`http://localhost:11434`, `15s`, `2`, `400ms`)
- Runtime applies model-aware Ollama request presets (timeout/retry/backoff plus optional `think`/temperature tuning) for newer/slower models.
- Task creation with `ai_provider=ollama` runs a 1-attempt structured-output viability preflight and blocks queueing when the selected model is non-viable.
- Settings can explicitly pull the recommended model (`gpt-oss:latest`) via `POST /tasks/ai-settings/ollama/ensure-recommended-model` (requires `confirm=true`).
- Model discovery and connection tests call Ollama `GET /api/tags`; connection test also attempts `GET /api/version`.

## Entrypoint Alignment

- Docker backend command uses `src.main_refactored:app`.
- Local development can use either `src.main_refactored:app` (recommended) or `src.main:app`.

## Task Review Runtime Behavior

- Task create payload supports `review_before_render_enabled` (boolean, default from user preference, initially `true`).
- Task create payload supports `timeline_editor_enabled` (boolean, default from user preference).
- When enabled, task processing stops after analysis at status `awaiting_review`.
- Users can edit draft clips through:
  - `GET /tasks/{task_id}/source-video`
  - `GET /tasks/{task_id}/draft-clips`
  - `POST /tasks/{task_id}/draft-clips` (create)
  - `PUT /tasks/{task_id}/draft-clips`
  - `DELETE /tasks/{task_id}/draft-clips/{draft_id}` (soft delete)
  - `POST /tasks/{task_id}/draft-clips/restore`
  - `POST /tasks/{task_id}/finalize`
- Finalize queues rendering from approved draft clips.
- Draft clip text is derived from transcript word timings inside each draft window (`start_time` -> `end_time`) when cache is available; AI-provided text is used as fallback.
- User preference `default_timeline_editor_enabled` controls the default timeline editor toggle for new tasks.
- User preference `default_review_before_render_enabled` controls whether new tasks default to pause at `awaiting_review`.

## Clip Selection Runtime Behavior

- AI transcript analysis asks for a larger candidate pool, then applies backend validation.
- For long transcripts, backend automatically analyzes in multiple transcript chunks, then runs a second-pass global rerank before final diversity filtering.
- Final clip candidates are capped by `MAX_CLIPS`.
- When `CLIP_DIVERSITY_ENABLED=true`, backend enforces timeline spread using:
  - bucket coverage (`CLIP_DIVERSITY_BUCKETS`)
  - start-time separation target (`CLIP_DIVERSITY_MIN_GAP_SECONDS`)

## Validation Checklist

When adding/changing a variable:
1. Update `backend/src/config.py`.
2. Update root env template (`.env.sample` in this repo; `.env.example` if present) and `backend/.env.example`.
3. Update this file.
4. Update references in `QUICKSTART.md` and `CLAUDE.md` if user-visible.

## YouTube Download Authentication

- Some YouTube videos now require signed-in cookies even for metadata access.
- When that happens, export a YouTube cookies file in Netscape format and set `YTDLP_COOKIES_FILE`.
- Docker compose mounts `backend/.secrets` into backend/worker containers at `/app/.secrets` (read-only), so a typical Docker value is:
  - `YTDLP_COOKIES_FILE=/app/.secrets/youtube.cookies.txt`
- Local non-Docker backend runs can point directly to a local path, for example:
  - `YTDLP_COOKIES_FILE=./.secrets/youtube.cookies.txt`
