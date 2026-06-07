-- Migration: add per-task transcription provider and encrypted AssemblyAI key storage.
-- Safe to run multiple times.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'tasks' AND column_name = 'transcription_provider'
    ) THEN
        ALTER TABLE tasks
        ADD COLUMN transcription_provider VARCHAR(20) NOT NULL DEFAULT 'local';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'check_tasks_transcription_provider'
    ) THEN
        ALTER TABLE tasks
        ADD CONSTRAINT check_tasks_transcription_provider
        CHECK (transcription_provider IN ('local', 'assemblyai'));
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'assembly_api_key_encrypted'
    ) THEN
        ALTER TABLE users
        ADD COLUMN assembly_api_key_encrypted TEXT;
    END IF;
END $$;

