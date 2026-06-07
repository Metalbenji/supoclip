#!/bin/bash
set -e

# Refresh fontconfig cache at every container start so that fonts added via
# volume mount (./backend/fonts:/app/fonts) are indexed for libass / ffmpeg.
fc-cache -fv /app/fonts 2>/dev/null || true

exec "$@"
