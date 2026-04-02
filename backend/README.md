# Backend

FastAPI service responsible for:
- source ingestion (YouTube/upload)
- transcription + transcript analysis
- clip rendering and storage
- task progress/status APIs
- optional AI focus tags that bias clip selection toward requested moment types

## Prerequisites

- Python 3.11+
- `uv`
- `ffmpeg`

Install ffmpeg:

```bash
# macOS
brew install ffmpeg

# Ubuntu
sudo apt update -y && sudo apt install ffmpeg -y

# Windows (Chocolatey)
choco install ffmpeg
```

## Local Development

```bash
cd backend
uv venv .venv
source .venv/bin/activate
uv sync
uvicorn src.main_refactored:app --reload --host 0.0.0.0 --port 8000
```

Legacy entrypoint (still present):

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

## Configuration

Use the root env file and canonical config reference:
- root `.env.sample`
- `docs/config.md`
- `docs/local-host-mappings.md`

Backend compatibility behavior:
- preferred model var: `LLM`
- legacy model var: `LLM_MODEL`
- clip selection vars:
  - `MAX_CLIPS`
  - `CLIP_DIVERSITY_ENABLED`
  - `CLIP_DIVERSITY_MIN_GAP_SECONDS`
  - `CLIP_DIVERSITY_BUCKETS`
  - long transcripts are analyzed in automatic AI chunks, then globally reranked in a second pass before diversity filtering
- AI provider keys: `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`, `ZAI_API_KEY`
- Ollama server config: `OLLAMA_BASE_URL` (used when provider is `ollama`)
- Ollama request-control env fallbacks:
  - `OLLAMA_TIMEOUT_SECONDS`
  - `OLLAMA_MAX_RETRIES`
  - `OLLAMA_RETRY_BACKOFF_MS`
- z.ai requests use Coding API endpoint: `https://api.z.ai/api/coding/paas/v4`
- z.ai supports user key profiles in Settings (`subscription`, `metered`) with routing mode (`auto`, `subscription`, `metered`)
- preferred Whisper var: `WHISPER_MODEL_SIZE`
- legacy Whisper var: `WHISPER_MODEL`
- local Whisper device vars:
  - `WHISPER_DEVICE`
  - `WHISPER_GPU_INDEX`
- local long-form Whisper vars:
  - `WHISPER_CHUNKING_ENABLED`
  - `WHISPER_CHUNK_DURATION_SECONDS`
  - `WHISPER_CHUNK_OVERLAP_SECONDS`
- transcription provider var: `TRANSCRIPTION_PROVIDER` (`local` default, `assemblyai` optional)
  - if AssemblyAI limits are exceeded (10h duration or local upload >2.2 GiB), backend falls back to local Whisper
- worker timeout var: `WORKER_JOB_TIMEOUT_SECONDS` (increase for multi-hour jobs)
- MediaPipe Tasks face model vars:
  - `MEDIAPIPE_FACE_MODEL_PATH`
  - `MEDIAPIPE_FACE_MODEL_URL`
  - `MEDIAPIPE_FACE_MODEL_SHA256`
  - `MEDIAPIPE_FACE_MODEL_AUTO_DOWNLOAD`

## Docker

Backend is started by `docker-compose.yml` with:
- app entrypoint: `src.main_refactored:app`
- worker: `src.workers.tasks.WorkerSettings`

## API Docs

When running locally or via Docker:
- Swagger UI: `http://${APP_HOST}:${BACKEND_HOST_PORT}/docs` (default `http://localhost:8000/docs`)
- Task runtime statuses include: `queued`, `processing`, `awaiting_review`, `completed`, `error`
- AI model discovery: `GET /tasks/ai-settings/{provider}/models`
  - key providers use saved user key first, then env fallback
  - `ollama` supports profile-aware model listing with auth + timeout/retry controls
  - `ollama` runtime applies model-aware request presets (timeout/retry/backoff and optional structured-output tuning fields)
- Legacy Ollama server settings (still supported):
  - `PUT /tasks/ai-settings/ollama/server`
  - `DELETE /tasks/ai-settings/ollama/server`
- Advanced Ollama settings:
  - `GET /tasks/ai-settings/ollama/profiles`
  - `PUT /tasks/ai-settings/ollama/profiles/{profile}`
  - `DELETE /tasks/ai-settings/ollama/profiles/{profile}`
  - `PUT /tasks/ai-settings/ollama/default-profile`
  - `PUT /tasks/ai-settings/ollama/request-controls`
  - `POST /tasks/ai-settings/ollama/test-connection`
  - `POST /tasks/ai-settings/ollama/ensure-recommended-model` (pulls `gpt-oss:latest` when explicitly confirmed)
  - `POST /tasks/ai-settings/ollama/test-model-viability`
  - `POST /tasks/` with `ai_provider=ollama` now runs a model viability preflight and rejects non-viable models before queueing
- z.ai profile keys:
  - `PUT /tasks/ai-settings/zai/profiles/{subscription|metered}/key`
  - `DELETE /tasks/ai-settings/zai/profiles/{subscription|metered}/key`
  - `PUT /tasks/ai-settings/zai/routing-mode` (`auto`, `subscription`, `metered`)
- Review-before-render endpoints:
  - `GET /tasks/{task_id}/source-video`
  - `GET /tasks/{task_id}/draft-clips`
  - `POST /tasks/{task_id}/draft-clips` (create)
  - `PUT /tasks/{task_id}/draft-clips`
  - `DELETE /tasks/{task_id}/draft-clips/{draft_id}` (soft delete)
- Task creation:
  - `POST /tasks/` accepts `ai_options.focus_tags` as an optional array of soft-preference tags used to bias transcript analysis and reranking
  - `POST /tasks/{task_id}/draft-clips/restore`
  - `POST /tasks/{task_id}/finalize`
  - `PATCH /tasks/{task_id}` supports per-task `timeline_editor_enabled`
- Draft clip text defaults to transcript words overlapping each clip's `start_time`/`end_time` window (AI text fallback when cache is unavailable).

## Fonts

- `GET /fonts`: list available subtitle fonts from `backend/fonts`.
- `POST /fonts/upload`: upload a new `.ttf` font file (available immediately in the frontend font dropdown).
- `GET /fonts/{font_name}`: serve a specific `.ttf` font for frontend preview loading.
- You can still add `.ttf` files manually to `backend/fonts/` if preferred.
- Install a curated top-10 free subtitle pack: `./backend/bin/install_subtitle_font_pack.sh`
- Pack details and references: `backend/fonts/FONT_PACK_TOP10.md`

## Admin Task API

- `POST /tasks/admin/cancel-all`: cancel all `queued`/`processing` tasks and drain queued ARQ jobs.
- `POST /tasks/admin/backfill-awaiting-review-subtitle-styles`: one-time backfill for missing/partial `tasks.subtitle_style` on `awaiting_review` tasks.
- `PATCH /tasks/admin/{task_id}/subtitle-style`: patch one task's subtitle style (for recovery when old tasks are missing custom style fields).
- If `ADMIN_API_KEY` is set, include it as `x-admin-key` request header.
- One-time CLI helper: `./backend/bin/backfill_awaiting_review_subtitle_styles.py --dry-run` (remove `--dry-run` to apply).
