-- Migration: add per-task AI provider and encrypted user LLM API keys.
-- Safe to run multiple times.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'tasks' AND column_name = 'ai_provider'
    ) THEN
        ALTER TABLE tasks
        ADD COLUMN ai_provider VARCHAR(20) NOT NULL DEFAULT 'openai';
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
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'openai_api_key_encrypted'
    ) THEN
        ALTER TABLE users
        ADD COLUMN openai_api_key_encrypted TEXT;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'google_api_key_encrypted'
    ) THEN
        ALTER TABLE users
        ADD COLUMN google_api_key_encrypted TEXT;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'anthropic_api_key_encrypted'
    ) THEN
        ALTER TABLE users
        ADD COLUMN anthropic_api_key_encrypted TEXT;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'zai_api_key_encrypted'
    ) THEN
        ALTER TABLE users
        ADD COLUMN zai_api_key_encrypted TEXT;
    END IF;
END $$;
