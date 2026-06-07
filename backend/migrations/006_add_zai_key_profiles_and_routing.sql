-- Migration: add z.ai key profiles (subscription/metered) and routing mode.

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS default_zai_key_routing_mode VARCHAR(20) NOT NULL DEFAULT 'auto';

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'check_users_default_zai_key_routing_mode'
    ) THEN
        ALTER TABLE users DROP CONSTRAINT check_users_default_zai_key_routing_mode;
    END IF;

    ALTER TABLE users
        ADD CONSTRAINT check_users_default_zai_key_routing_mode
        CHECK (default_zai_key_routing_mode IN ('auto', 'subscription', 'metered'));
END $$;

CREATE TABLE IF NOT EXISTS user_ai_key_profiles (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider VARCHAR(20) NOT NULL,
    profile_name VARCHAR(30) NOT NULL,
    api_key_encrypted TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT check_user_ai_key_profiles_provider
        CHECK (provider IN ('openai', 'google', 'anthropic', 'zai')),
    CONSTRAINT check_user_ai_key_profiles_profile_name
        CHECK (profile_name IN ('subscription', 'metered'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_ai_key_profiles_user_provider_profile
    ON user_ai_key_profiles(user_id, provider, profile_name);
