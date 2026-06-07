-- Migration: add Ollama as an AI provider and persist per-user Ollama server URL.
-- Safe to run multiple times.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'default_ollama_base_url'
    ) THEN
        ALTER TABLE users
        ADD COLUMN default_ollama_base_url VARCHAR(500);
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'check_tasks_ai_provider'
    ) THEN
        ALTER TABLE tasks
        DROP CONSTRAINT check_tasks_ai_provider;
    END IF;
    ALTER TABLE tasks
    ADD CONSTRAINT check_tasks_ai_provider
    CHECK (ai_provider IN ('openai', 'google', 'anthropic', 'zai', 'ollama'));
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
