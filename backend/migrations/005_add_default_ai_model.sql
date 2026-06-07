-- Migration: add user-level default AI model override.
-- Safe to run multiple times.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'default_ai_model'
    ) THEN
        ALTER TABLE users
        ADD COLUMN default_ai_model VARCHAR(100);
    END IF;
END $$;
