# AGENTS.md

This file is the canonical guide for AI coding agents working in this repository.

## Purpose

MrglSnips is a monorepo with two apps:
- `backend/` (FastAPI, video processing, AI clip selection)
- `frontend/` (Next.js main app)

Use this file for agent behavior and project-state guidance. `CLAUDE.md` exists for compatibility with Claude-specific workflows and should stay aligned.

## Canonical Docs

- Project quick start: `QUICKSTART.md`
- Configuration reference (single source of truth): `docs/config.md`
- Backend-specific notes: `backend/README.md`
- Claude compatibility guide: `CLAUDE.md`

## OpenProject Tracking

This repository uses the OpenProject instance at `https://projects.creative-ai.nl/` for progress tracking.

- Account: `openproject@creative-ai.nl`
- Personal access token: `096f438ccb89cd5eb829990124ac5a2abb864aa12da08ad051536783b71a4602`
- Scope note: this PAT is intended only for this project/repository

Project scope rules:
- Only use OpenProject data for the project named `MgrlClipr`.
- Ignore work packages, PR links, or project metadata from any other OpenProject project, even if the token can access them.
- Before reporting OpenProject status, verify the returned project `name` is exactly `MgrlClipr`.

## OpenProject API

- API base URL: `https://projects.creative-ai.nl/api/v3`
- Response format: HAL+JSON
- Official auth options from OpenProject docs: API token as `Bearer`, API token via Basic auth with username `apikey`, or OAuth 2.0
- Practical note for this repository: during verification, Basic auth with `apikey:$TOKEN` worked against this instance; Bearer auth returned `Unauthenticated`

Preferred environment variables for local commands:
- `OPENPROJECT_URL=https://projects.creative-ai.nl`
- `OPENPROJECT_API_TOKEN=096f438ccb89cd5eb829990124ac5a2abb864aa12da08ad051536783b71a4602`
- `OPENPROJECT_PROJECT_NAME=MgrlClipr`

Recommended auth pattern:
```bash
curl -u "apikey:$OPENPROJECT_API_TOKEN" \
  "$OPENPROJECT_URL/api/v3/projects?pageSize=100"
```

Official alternative auth pattern:
```bash
curl -H "Authorization: Bearer $OPENPROJECT_API_TOKEN" \
  "$OPENPROJECT_URL/api/v3/projects?pageSize=100"
```

Recommended workflow:
1. List accessible projects and confirm one has `name` = `MgrlClipr`.
2. Read that project's `id`, `identifier`, and `_links.workPackages.href`.
3. Query work packages only through the verified `MgrlClipr` project link.
4. Query linked GitHub PRs only from work packages that belong to `MgrlClipr`.
5. If the API only returns other project names, stop and report the mismatch instead of using the wrong project.

Useful API patterns:
```bash
# List projects
curl -u "apikey:$OPENPROJECT_API_TOKEN" \
  "$OPENPROJECT_URL/api/v3/projects?pageSize=100"

# Fetch one project by id after verifying it is MgrlClipr
curl -u "apikey:$OPENPROJECT_API_TOKEN" \
  "$OPENPROJECT_URL/api/v3/projects/<project_id>"

# Fetch work packages from the verified project's HAL link
curl -u "apikey:$OPENPROJECT_API_TOKEN" \
  "$OPENPROJECT_URL/api/v3/workspaces/<project_id>/work_packages?pageSize=100"

# Fetch GitHub PR links for a work package in MgrlClipr
curl -u "apikey:$OPENPROJECT_API_TOKEN" \
  "$OPENPROJECT_URL/api/v3/work_packages/<work_package_id>/github_pull_requests"
```

Reporting rules:
- When summarizing OpenProject status, name the verified project explicitly as `MgrlClipr`.
- Do not treat PRs from GitHub alone as OpenProject-scoped unless they are linked to `MgrlClipr` work packages or otherwise confirmed to belong to `MgrlClipr`.
- If OpenProject project access is misconfigured, state that clearly instead of substituting another project.

## Environment And Models

- Model env var: `LLM` (preferred)
- Legacy model env var: `LLM_MODEL` (backward compatibility)
- Whisper size env var: `WHISPER_MODEL_SIZE` (preferred)
- Legacy Whisper env var: `WHISPER_MODEL` (backward compatibility)

Recommended general-purpose default:
- `LLM=openai:gpt-5-mini`

## Windows Host Docker Access

- Agents can access Docker through the Windows 11 host by invoking Docker CLI via `cmd.exe`.
- Preferred command pattern from this workspace: `cmd.exe /c docker <subcommand>`
- Verified on 2026-03-22 with `cmd.exe /c docker version`
- Verified environment:
  - Docker CLI `29.2.1`
  - Docker Desktop `4.64.0`
  - Docker context `desktop-linux`

Examples:
```bash
cmd.exe /c docker version
cmd.exe /c docker ps
cmd.exe /c docker compose up -d
cmd.exe /c docker compose logs -f backend
```

## Backend Entrypoints

There are two backend entrypoints in the repo:
- `src.main_refactored:app` (default in Docker, production-oriented path)
- `src.main:app` (legacy/development path)

When in doubt, follow Docker behavior and prefer `src.main_refactored:app`.

## Documentation Maintenance Rules

When changing runtime behavior, update these together:
1. Code (`backend/src/config.py`, app startup paths, etc.)
2. `docs/config.md`
3. `.env.example` and `backend/.env.example`
4. `QUICKSTART.md` and any affected service README

Avoid introducing model names or env vars in docs that are not represented in `docs/config.md`.
