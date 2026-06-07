-- Migration: add user-level local Whisper device preferences.
-- Safe to run multiple times.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'default_whisper_device'
    ) THEN
        ALTER TABLE users
        ADD COLUMN default_whisper_device VARCHAR(20) NOT NULL DEFAULT 'auto';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'default_whisper_gpu_index'
    ) THEN
        ALTER TABLE users
        ADD COLUMN default_whisper_gpu_index INTEGER NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'check_users_default_whisper_device'
    ) THEN
        ALTER TABLE users
        DROP CONSTRAINT check_users_default_whisper_device;
    END IF;
    ALTER TABLE users
    ADD CONSTRAINT check_users_default_whisper_device
    CHECK (default_whisper_device IN ('auto', 'cpu', 'gpu'));
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'check_users_default_whisper_gpu_index'
    ) THEN
        ALTER TABLE users
        DROP CONSTRAINT check_users_default_whisper_gpu_index;
    END IF;
    ALTER TABLE users
    ADD CONSTRAINT check_users_default_whisper_gpu_index
    CHECK (default_whisper_gpu_index IS NULL OR default_whisper_gpu_index >= 0);
END $$;
