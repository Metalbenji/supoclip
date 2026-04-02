-- Add user-level defaults for local Whisper model size / quality preset.
ALTER TABLE "users"
ADD COLUMN IF NOT EXISTS "default_whisper_model_size" VARCHAR(20) DEFAULT 'medium';

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'check_users_default_whisper_model_size'
  ) THEN
    ALTER TABLE "users"
    DROP CONSTRAINT check_users_default_whisper_model_size;
  END IF;
  ALTER TABLE "users"
  ADD CONSTRAINT check_users_default_whisper_model_size
  CHECK ("default_whisper_model_size" IN ('tiny', 'base', 'small', 'medium', 'large', 'turbo'));
END $$;
