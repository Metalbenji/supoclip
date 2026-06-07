-- Migration: add user-level default processing settings.
-- Safe to run multiple times.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'default_transitions_enabled'
    ) THEN
        ALTER TABLE users
        ADD COLUMN default_transitions_enabled BOOLEAN NOT NULL DEFAULT false;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'default_transcription_provider'
    ) THEN
        ALTER TABLE users
        ADD COLUMN default_transcription_provider VARCHAR(20) NOT NULL DEFAULT 'local';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'check_users_default_transcription_provider'
    ) THEN
        ALTER TABLE users
        ADD CONSTRAINT check_users_default_transcription_provider
        CHECK (default_transcription_provider IN ('local', 'assemblyai'));
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'default_ai_provider'
    ) THEN
        ALTER TABLE users
        ADD COLUMN default_ai_provider VARCHAR(20) NOT NULL DEFAULT 'openai';
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'check_users_default_ai_provider'
    ) THEN
        ALTER TABLE users
        DROP CONSTRAINT check_users_default_ai_provider;
    END IF;
    ALTER TABLE users
    ADD CONSTRAINT check_users_default_ai_provider
    CHECK (default_ai_provider IN ('openai', 'google', 'anthropic', 'zai', 'ollama'));
END $$;
