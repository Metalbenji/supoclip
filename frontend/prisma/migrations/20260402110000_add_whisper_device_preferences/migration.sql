-- Add user-level defaults for local Whisper device preference and optional GPU index.
ALTER TABLE "users"
ADD COLUMN IF NOT EXISTS "default_whisper_device" VARCHAR(20) DEFAULT 'auto';

ALTER TABLE "users"
ADD COLUMN IF NOT EXISTS "default_whisper_gpu_index" INTEGER;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'check_users_default_whisper_device'
  ) THEN
    ALTER TABLE "users"
    DROP CONSTRAINT check_users_default_whisper_device;
  END IF;
  ALTER TABLE "users"
  ADD CONSTRAINT check_users_default_whisper_device
  CHECK ("default_whisper_device" IN ('auto', 'cpu', 'gpu'));
END $$;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'check_users_default_whisper_gpu_index'
  ) THEN
    ALTER TABLE "users"
    DROP CONSTRAINT check_users_default_whisper_gpu_index;
  END IF;
  ALTER TABLE "users"
  ADD CONSTRAINT check_users_default_whisper_gpu_index
  CHECK ("default_whisper_gpu_index" IS NULL OR "default_whisper_gpu_index" >= 0);
END $$;
