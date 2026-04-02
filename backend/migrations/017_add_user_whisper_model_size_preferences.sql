-- Migration: add user-level local Whisper model-size preference.
-- Safe to run multiple times.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'default_whisper_model_size'
    ) THEN
        ALTER TABLE users
        ADD COLUMN default_whisper_model_size VARCHAR(20) NOT NULL DEFAULT 'medium';
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'check_users_default_whisper_model_size'
    ) THEN
        ALTER TABLE users
        DROP CONSTRAINT check_users_default_whisper_model_size;
    END IF;
    ALTER TABLE users
    ADD CONSTRAINT check_users_default_whisper_model_size
    CHECK (default_whisper_model_size IN ('tiny', 'base', 'small', 'medium', 'large', 'turbo'));
END $$;
