-- Add user-level defaults for local Whisper chunking and per-task timeout.
ALTER TABLE "users"
ADD COLUMN IF NOT EXISTS "default_whisper_chunking_enabled" BOOLEAN DEFAULT true;

ALTER TABLE "users"
ADD COLUMN IF NOT EXISTS "default_whisper_chunk_duration_seconds" INTEGER DEFAULT 1200;

ALTER TABLE "users"
ADD COLUMN IF NOT EXISTS "default_whisper_chunk_overlap_seconds" INTEGER DEFAULT 8;

ALTER TABLE "users"
ADD COLUMN IF NOT EXISTS "default_task_timeout_seconds" INTEGER DEFAULT 21600;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'check_users_default_whisper_chunk_duration_seconds'
  ) THEN
    ALTER TABLE "users"
    ADD CONSTRAINT check_users_default_whisper_chunk_duration_seconds
    CHECK ("default_whisper_chunk_duration_seconds" BETWEEN 300 AND 3600);
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'check_users_default_whisper_chunk_overlap_seconds'
  ) THEN
    ALTER TABLE "users"
    ADD CONSTRAINT check_users_default_whisper_chunk_overlap_seconds
    CHECK ("default_whisper_chunk_overlap_seconds" BETWEEN 0 AND 120);
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'check_users_default_task_timeout_seconds'
  ) THEN
    ALTER TABLE "users"
    ADD CONSTRAINT check_users_default_task_timeout_seconds
    CHECK ("default_task_timeout_seconds" BETWEEN 300 AND 86400);
  END IF;
END $$;
