-- Migration: advanced Ollama support with profiles, auth, and request controls.
-- Safe to run multiple times.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'default_ollama_profile'
    ) THEN
        ALTER TABLE users
        ADD COLUMN default_ollama_profile VARCHAR(100);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'default_ollama_timeout_seconds'
    ) THEN
        ALTER TABLE users
        ADD COLUMN default_ollama_timeout_seconds INTEGER;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'default_ollama_max_retries'
    ) THEN
        ALTER TABLE users
        ADD COLUMN default_ollama_max_retries INTEGER;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'default_ollama_retry_backoff_ms'
    ) THEN
        ALTER TABLE users
        ADD COLUMN default_ollama_retry_backoff_ms INTEGER;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'check_users_default_ollama_timeout_seconds'
    ) THEN
        ALTER TABLE users DROP CONSTRAINT check_users_default_ollama_timeout_seconds;
    END IF;

    ALTER TABLE users
    ADD CONSTRAINT check_users_default_ollama_timeout_seconds
    CHECK (
        default_ollama_timeout_seconds IS NULL
        OR default_ollama_timeout_seconds BETWEEN 1 AND 600
    );
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'check_users_default_ollama_max_retries'
    ) THEN
        ALTER TABLE users DROP CONSTRAINT check_users_default_ollama_max_retries;
    END IF;

    ALTER TABLE users
    ADD CONSTRAINT check_users_default_ollama_max_retries
    CHECK (
        default_ollama_max_retries IS NULL
        OR default_ollama_max_retries BETWEEN 0 AND 10
    );
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'check_users_default_ollama_retry_backoff_ms'
    ) THEN
        ALTER TABLE users DROP CONSTRAINT check_users_default_ollama_retry_backoff_ms;
    END IF;

    ALTER TABLE users
    ADD CONSTRAINT check_users_default_ollama_retry_backoff_ms
    CHECK (
        default_ollama_retry_backoff_ms IS NULL
        OR default_ollama_retry_backoff_ms BETWEEN 0 AND 30000
    );
END $$;

CREATE TABLE IF NOT EXISTS user_ollama_server_profiles (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    profile_name VARCHAR(100) NOT NULL,
    base_url VARCHAR(500) NOT NULL,
    auth_mode VARCHAR(20) NOT NULL DEFAULT 'none',
    auth_header_name VARCHAR(100),
    auth_secret_encrypted TEXT,
    enabled BOOLEAN NOT NULL DEFAULT true,
    is_default BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT check_user_ollama_server_profiles_auth_mode
        CHECK (auth_mode IN ('none', 'bearer', 'custom_header'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_ollama_server_profiles_user_profile
    ON user_ollama_server_profiles(user_id, profile_name);

CREATE INDEX IF NOT EXISTS idx_user_ollama_server_profiles_user_default
    ON user_ollama_server_profiles(user_id, is_default);

INSERT INTO user_ollama_server_profiles (
    id,
    user_id,
    profile_name,
    base_url,
    auth_mode,
    auth_header_name,
    auth_secret_encrypted,
    enabled,
    is_default,
    created_at,
    updated_at
)
SELECT
    md5(random()::text || clock_timestamp()::text || u.id),
    u.id,
    'default',
    TRIM(u.default_ollama_base_url),
    'none',
    NULL,
    NULL,
    true,
    true,
    NOW(),
    NOW()
FROM users u
WHERE COALESCE(TRIM(u.default_ollama_base_url), '') <> ''
  AND NOT EXISTS (
      SELECT 1
      FROM user_ollama_server_profiles p
      WHERE p.user_id = u.id
        AND p.profile_name = 'default'
  );

UPDATE users u
SET default_ollama_profile = 'default'
WHERE COALESCE(TRIM(u.default_ollama_profile), '') = ''
  AND EXISTS (
      SELECT 1
      FROM user_ollama_server_profiles p
      WHERE p.user_id = u.id
        AND p.profile_name = 'default'
  );

UPDATE user_ollama_server_profiles p
SET is_default = CASE
    WHEN COALESCE(NULLIF(TRIM(u.default_ollama_profile), ''), 'default') = p.profile_name THEN true
    ELSE false
END,
updated_at = NOW()
FROM users u
WHERE p.user_id = u.id;

UPDATE users u
SET default_ollama_profile = profile_rows.profile_name
FROM (
    SELECT DISTINCT ON (p.user_id)
        p.user_id,
        p.profile_name
    FROM user_ollama_server_profiles p
    WHERE p.enabled = true
    ORDER BY p.user_id, p.is_default DESC, p.updated_at DESC, p.profile_name ASC
) AS profile_rows
WHERE u.id = profile_rows.user_id
  AND COALESCE(TRIM(u.default_ollama_profile), '') = '';

UPDATE user_ollama_server_profiles p
SET is_default = (p.profile_name = u.default_ollama_profile),
    updated_at = NOW()
FROM users u
WHERE p.user_id = u.id
  AND COALESCE(TRIM(u.default_ollama_profile), '') <> '';
