"""
Shared transcription provider limits and fallback behavior.
"""

from __future__ import annotations

ASSEMBLYAI_MAX_DURATION_SECONDS = 10 * 60 * 60  # 10 hours
ASSEMBLYAI_MAX_REMOTE_FILE_SIZE_BYTES = 5 * 1024 * 1024 * 1024  # 5 GiB
# Current backend flow uploads local files to AssemblyAI, which has a lower cap.
ASSEMBLYAI_MAX_LOCAL_UPLOAD_SIZE_BYTES = int(2.2 * 1024 * 1024 * 1024)  # ~2.2 GiB

