import os

from dotenv import load_dotenv
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text

# Load environment variables
load_dotenv()

# Database configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://localhost:5432/supoclip"
)

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL query logging
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
)

# Create async session maker
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Base class for all models
class Base(DeclarativeBase):
    pass

# Dependency to get database session
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

# Initialize database
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                """
                ALTER TABLE tasks
                ADD COLUMN IF NOT EXISTS transcription_provider VARCHAR(20) NOT NULL DEFAULT 'local'
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE sources
                ADD COLUMN IF NOT EXISTS url TEXT
                """
            )
        )
        await conn.execute(
            text(
                """
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
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS assembly_api_key_encrypted TEXT
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS youtube_cookies_encrypted TEXT
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS youtube_cookies_filename VARCHAR(255)
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS youtube_cookies_updated_at TIMESTAMPTZ
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE tasks
                ADD COLUMN IF NOT EXISTS ai_provider VARCHAR(20) NOT NULL DEFAULT 'openai'
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE tasks
                ADD COLUMN IF NOT EXISTS review_before_render_enabled BOOLEAN NOT NULL DEFAULT true
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE tasks
                ADD COLUMN IF NOT EXISTS timeline_editor_enabled BOOLEAN NOT NULL DEFAULT true
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE tasks
                ADD COLUMN IF NOT EXISTS transitions_enabled BOOLEAN NOT NULL DEFAULT false
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE tasks
                ADD COLUMN IF NOT EXISTS subtitle_style JSONB
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE tasks
                ADD COLUMN IF NOT EXISTS ai_focus_tags JSONB
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE tasks
                ADD COLUMN IF NOT EXISTS processing_profile VARCHAR(32) NOT NULL DEFAULT 'balanced'
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE tasks
                ADD COLUMN IF NOT EXISTS runtime_info_json JSONB
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE tasks
                ADD COLUMN IF NOT EXISTS failure_code VARCHAR(40)
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE tasks
                ADD COLUMN IF NOT EXISTS failure_hint TEXT
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE tasks
                ADD COLUMN IF NOT EXISTS stage_checkpoint VARCHAR(32) NOT NULL DEFAULT 'queued'
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE tasks
                ADD COLUMN IF NOT EXISTS retryable_from_stages JSONB
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'check_tasks_ai_provider'
                    ) THEN
                        ALTER TABLE tasks DROP CONSTRAINT check_tasks_ai_provider;
                    END IF;
                    ALTER TABLE tasks
                    ADD CONSTRAINT check_tasks_ai_provider
                    CHECK (ai_provider IN ('openai', 'google', 'anthropic', 'zai', 'ollama'));
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS openai_api_key_encrypted TEXT
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS google_api_key_encrypted TEXT
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS anthropic_api_key_encrypted TEXT
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS zai_api_key_encrypted TEXT
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_transitions_enabled BOOLEAN NOT NULL DEFAULT false
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_review_before_render_enabled BOOLEAN NOT NULL DEFAULT true
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_timeline_editor_enabled BOOLEAN NOT NULL DEFAULT true
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_processing_profile VARCHAR(32) NOT NULL DEFAULT 'balanced'
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_framing_mode VARCHAR(32) NOT NULL DEFAULT 'auto'
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_face_detection_mode VARCHAR(20) NOT NULL DEFAULT 'balanced'
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_fallback_crop_position VARCHAR(20) NOT NULL DEFAULT 'center'
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_face_anchor_profile VARCHAR(24) NOT NULL DEFAULT 'auto'
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_transcription_provider VARCHAR(20) NOT NULL DEFAULT 'local'
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_whisper_chunking_enabled BOOLEAN NOT NULL DEFAULT true
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_whisper_chunk_duration_seconds INTEGER NOT NULL DEFAULT 1200
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_whisper_chunk_overlap_seconds INTEGER NOT NULL DEFAULT 8
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_task_timeout_seconds INTEGER NOT NULL DEFAULT 21600
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_whisper_device VARCHAR(20) NOT NULL DEFAULT 'auto'
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_whisper_model_size VARCHAR(20) NOT NULL DEFAULT 'medium'
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_whisper_gpu_index INTEGER NULL
                """
            )
        )
        await conn.execute(
            text(
                """
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
                """
            )
        )
        await conn.execute(
            text(
                """
                UPDATE users
                SET
                    default_framing_mode = CASE
                        WHEN COALESCE(NULLIF(TRIM(default_framing_mode), ''), 'auto') = 'disable_face_crop'
                            THEN 'fixed_position'
                        ELSE COALESCE(NULLIF(TRIM(default_framing_mode), ''), 'auto')
                    END,
                    default_face_detection_mode = CASE
                        WHEN COALESCE(NULLIF(TRIM(default_face_detection_mode), ''), 'balanced') = 'center_only'
                            THEN 'balanced'
                        ELSE COALESCE(NULLIF(TRIM(default_face_detection_mode), ''), 'balanced')
                    END,
                    default_fallback_crop_position = COALESCE(NULLIF(TRIM(default_fallback_crop_position), ''), 'center')
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'check_users_default_face_anchor_profile'
                    ) THEN
                        ALTER TABLE users DROP CONSTRAINT check_users_default_face_anchor_profile;
                    END IF;
                    ALTER TABLE users
                    ADD CONSTRAINT check_users_default_face_anchor_profile
                    CHECK (default_face_anchor_profile IN ('auto', 'left_only', 'left_or_center', 'center_only', 'right_or_center', 'right_only'));
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'check_users_default_processing_profile'
                    ) THEN
                        ALTER TABLE users DROP CONSTRAINT check_users_default_processing_profile;
                    END IF;
                    ALTER TABLE users
                    ADD CONSTRAINT check_users_default_processing_profile
                    CHECK (default_processing_profile IN ('fast_draft', 'balanced', 'best_quality', 'stream_layout'));
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'check_tasks_processing_profile'
                    ) THEN
                        ALTER TABLE tasks DROP CONSTRAINT check_tasks_processing_profile;
                    END IF;
                    ALTER TABLE tasks
                    ADD CONSTRAINT check_tasks_processing_profile
                    CHECK (processing_profile IN ('fast_draft', 'balanced', 'best_quality', 'stream_layout'));
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'check_tasks_stage_checkpoint'
                    ) THEN
                        ALTER TABLE tasks DROP CONSTRAINT check_tasks_stage_checkpoint;
                    END IF;
                    ALTER TABLE tasks
                    ADD CONSTRAINT check_tasks_stage_checkpoint
                    CHECK (stage_checkpoint IN ('queued', 'started', 'downloaded', 'transcribed', 'analyzed', 'review_approved', 'completed', 'failed'));
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'check_users_default_framing_mode'
                    ) THEN
                        ALTER TABLE users DROP CONSTRAINT check_users_default_framing_mode;
                    END IF;
                    ALTER TABLE users
                    ADD CONSTRAINT check_users_default_framing_mode
                    CHECK (default_framing_mode IN ('auto', 'prefer_face', 'fixed_position'));
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'check_users_default_face_detection_mode'
                    ) THEN
                        ALTER TABLE users DROP CONSTRAINT check_users_default_face_detection_mode;
                    END IF;
                    ALTER TABLE users
                    ADD CONSTRAINT check_users_default_face_detection_mode
                    CHECK (default_face_detection_mode IN ('balanced', 'more_faces'));
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'check_users_default_fallback_crop_position'
                    ) THEN
                        ALTER TABLE users DROP CONSTRAINT check_users_default_fallback_crop_position;
                    END IF;
                    ALTER TABLE users
                    ADD CONSTRAINT check_users_default_fallback_crop_position
                    CHECK (default_fallback_crop_position IN ('center', 'left_center', 'right_center'));
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'check_users_default_whisper_model_size'
                    ) THEN
                        ALTER TABLE users DROP CONSTRAINT check_users_default_whisper_model_size;
                    END IF;
                    ALTER TABLE users
                    ADD CONSTRAINT check_users_default_whisper_model_size
                    CHECK (default_whisper_model_size IN ('tiny', 'base', 'small', 'medium', 'large', 'turbo'));
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'check_users_default_whisper_device'
                    ) THEN
                        ALTER TABLE users DROP CONSTRAINT check_users_default_whisper_device;
                    END IF;
                    ALTER TABLE users
                    ADD CONSTRAINT check_users_default_whisper_device
                    CHECK (default_whisper_device IN ('auto', 'cpu', 'gpu'));
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'check_users_default_whisper_gpu_index'
                    ) THEN
                        ALTER TABLE users DROP CONSTRAINT check_users_default_whisper_gpu_index;
                    END IF;
                    ALTER TABLE users
                    ADD CONSTRAINT check_users_default_whisper_gpu_index
                    CHECK (default_whisper_gpu_index IS NULL OR default_whisper_gpu_index >= 0);
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'check_users_default_whisper_chunk_duration_seconds'
                    ) THEN
                        ALTER TABLE users DROP CONSTRAINT check_users_default_whisper_chunk_duration_seconds;
                    END IF;
                    ALTER TABLE users
                    ADD CONSTRAINT check_users_default_whisper_chunk_duration_seconds
                    CHECK (default_whisper_chunk_duration_seconds BETWEEN 300 AND 3600);
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'check_users_default_whisper_chunk_overlap_seconds'
                    ) THEN
                        ALTER TABLE users DROP CONSTRAINT check_users_default_whisper_chunk_overlap_seconds;
                    END IF;
                    ALTER TABLE users
                    ADD CONSTRAINT check_users_default_whisper_chunk_overlap_seconds
                    CHECK (default_whisper_chunk_overlap_seconds BETWEEN 0 AND 120);
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'check_users_default_task_timeout_seconds'
                    ) THEN
                        ALTER TABLE users DROP CONSTRAINT check_users_default_task_timeout_seconds;
                    END IF;
                    ALTER TABLE users
                    ADD CONSTRAINT check_users_default_task_timeout_seconds
                    CHECK (default_task_timeout_seconds BETWEEN 300 AND 86400);
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_ai_provider VARCHAR(20) NOT NULL DEFAULT 'openai'
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_ollama_base_url VARCHAR(500)
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_ollama_profile VARCHAR(100)
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_ollama_timeout_seconds INTEGER
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_ollama_max_retries INTEGER
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_ollama_retry_backoff_ms INTEGER
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_ai_model VARCHAR(100)
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_font_weight INTEGER DEFAULT 600
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_highlight_color VARCHAR(7) DEFAULT '#FDE047'
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_line_height DOUBLE PRECISION DEFAULT 1.4
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_letter_spacing INTEGER DEFAULT 0
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_text_transform VARCHAR(20) DEFAULT 'none'
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_text_align VARCHAR(10) DEFAULT 'center'
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_stroke_color VARCHAR(7) DEFAULT '#000000'
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_stroke_width INTEGER DEFAULT 2
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_stroke_blur DOUBLE PRECISION DEFAULT 0.6
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_shadow_color VARCHAR(7) DEFAULT '#000000'
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_shadow_opacity DOUBLE PRECISION DEFAULT 0.5
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_shadow_blur INTEGER DEFAULT 2
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_shadow_offset_x INTEGER DEFAULT 0
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_shadow_offset_y INTEGER DEFAULT 2
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'check_users_default_text_transform'
                    ) THEN
                        ALTER TABLE users DROP CONSTRAINT check_users_default_text_transform;
                    END IF;
                    ALTER TABLE users
                    ADD CONSTRAINT check_users_default_text_transform
                    CHECK (default_text_transform IN ('none', 'uppercase', 'lowercase', 'capitalize'));
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'check_users_default_text_align'
                    ) THEN
                        ALTER TABLE users DROP CONSTRAINT check_users_default_text_align;
                    END IF;
                    ALTER TABLE users
                    ADD CONSTRAINT check_users_default_text_align
                    CHECK (default_text_align IN ('left', 'center', 'right'));
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'check_users_default_ai_provider'
                    ) THEN
                        ALTER TABLE users DROP CONSTRAINT check_users_default_ai_provider;
                    END IF;
                    ALTER TABLE users
                    ADD CONSTRAINT check_users_default_ai_provider
                    CHECK (default_ai_provider IN ('openai', 'google', 'anthropic', 'zai', 'ollama'));
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS default_zai_key_routing_mode VARCHAR(20) NOT NULL DEFAULT 'auto'
                """
            )
        )
        await conn.execute(
            text(
                """
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
                """
            )
        )
        await conn.execute(
            text(
                """
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
                """
            )
        )
        await conn.execute(
            text(
                """
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
                """
            )
        )
        await conn.execute(
            text(
                """
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
                """
            )
        )
        await conn.execute(
            text(
                """
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
                )
                """
            )
        )
        await conn.execute(
            text(
                """
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
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS task_clip_drafts (
                    id VARCHAR(36) PRIMARY KEY,
                    task_id VARCHAR(36) NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    clip_order INTEGER NOT NULL,
                    start_time VARCHAR(20) NOT NULL,
                    end_time VARCHAR(20) NOT NULL,
                    duration FLOAT NOT NULL,
                    original_start_time VARCHAR(20) NOT NULL,
                    original_end_time VARCHAR(20) NOT NULL,
                    original_duration FLOAT NOT NULL,
                    original_text TEXT,
                    edited_text TEXT,
                    relevance_score FLOAT NOT NULL,
                    review_score FLOAT NOT NULL DEFAULT 0,
                    feedback_score_adjustment FLOAT NOT NULL DEFAULT 0,
                    feedback_signals_json JSONB,
                    framing_metadata_json JSONB,
                    framing_mode_override VARCHAR(32) NOT NULL DEFAULT 'auto',
                    reasoning TEXT,
                    created_by_user BOOLEAN NOT NULL DEFAULT false,
                    is_selected BOOLEAN NOT NULL DEFAULT true,
                    is_deleted BOOLEAN NOT NULL DEFAULT false,
                    edited_word_timings_json JSONB,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS task_clip_drafts
                ADD COLUMN IF NOT EXISTS original_start_time VARCHAR(20)
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS task_clip_drafts
                ADD COLUMN IF NOT EXISTS original_end_time VARCHAR(20)
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS task_clip_drafts
                ADD COLUMN IF NOT EXISTS original_duration FLOAT
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS task_clip_drafts
                ADD COLUMN IF NOT EXISTS created_by_user BOOLEAN NOT NULL DEFAULT false
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS task_clip_drafts
                ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT false
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS task_clip_drafts
                ADD COLUMN IF NOT EXISTS review_score FLOAT NOT NULL DEFAULT 0
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS task_clip_drafts
                ADD COLUMN IF NOT EXISTS feedback_score_adjustment FLOAT NOT NULL DEFAULT 0
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS task_clip_drafts
                ADD COLUMN IF NOT EXISTS feedback_signals_json JSONB
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS task_clip_drafts
                ADD COLUMN IF NOT EXISTS framing_metadata_json JSONB
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS task_clip_drafts
                ADD COLUMN IF NOT EXISTS framing_mode_override VARCHAR(32) NOT NULL DEFAULT 'auto'
                """
            )
        )
        await conn.execute(
            text(
                """
                UPDATE task_clip_drafts
                SET original_start_time = COALESCE(original_start_time, start_time),
                    original_end_time = COALESCE(original_end_time, end_time),
                    original_duration = COALESCE(original_duration, duration)
                """
            )
        )
        await conn.execute(
            text(
                """
                UPDATE task_clip_drafts
                SET review_score = COALESCE(review_score, relevance_score),
                    feedback_score_adjustment = COALESCE(feedback_score_adjustment, 0),
                    feedback_signals_json = COALESCE(feedback_signals_json, '{}'::jsonb),
                    framing_metadata_json = COALESCE(framing_metadata_json, '{}'::jsonb),
                    framing_mode_override = CASE
                        WHEN COALESCE(NULLIF(TRIM(framing_mode_override), ''), 'auto') = 'disable_face_crop'
                            THEN 'fixed_position'
                        ELSE COALESCE(NULLIF(TRIM(framing_mode_override), ''), 'auto')
                    END
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS task_clip_drafts
                ALTER COLUMN original_start_time SET NOT NULL
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS task_clip_drafts
                ALTER COLUMN original_end_time SET NOT NULL
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE IF EXISTS task_clip_drafts
                ALTER COLUMN original_duration SET NOT NULL
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_task_clip_drafts_task_id
                    ON task_clip_drafts(task_id)
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_task_clip_drafts_clip_order
                    ON task_clip_drafts(clip_order)
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_task_clip_drafts_task_order
                    ON task_clip_drafts(task_id, clip_order)
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_task_clip_drafts_active
                    ON task_clip_drafts(task_id, is_deleted)
                """
            )
        )
        await conn.execute(
            text(
                """
                COMMENT ON COLUMN task_clip_drafts.framing_metadata_json IS 'Structured face/framing analysis used for review-time framing guidance and crop defaults.'
                """
            )
        )
        await conn.execute(
            text(
                """
                COMMENT ON COLUMN task_clip_drafts.framing_mode_override IS 'Per-draft framing override: auto, prefer_face, or fixed_position.'
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_user_ai_key_profiles_user_provider_profile
                    ON user_ai_key_profiles(user_id, provider, profile_name)
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_user_ollama_server_profiles_user_profile
                    ON user_ollama_server_profiles(user_id, profile_name)
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_user_ollama_server_profiles_user_default
                    ON user_ollama_server_profiles(user_id, is_default)
                """
            )
        )
        await conn.execute(
            text(
                """
                INSERT INTO user_ollama_server_profiles (
                    id,
                    user_id,
                    profile_name,
                    base_url,
                    auth_mode,
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
                  )
                """
            )
        )
        await conn.execute(
            text(
                """
                UPDATE users u
                SET default_ollama_profile = 'default'
                WHERE COALESCE(TRIM(u.default_ollama_profile), '') = ''
                  AND EXISTS (
                      SELECT 1
                      FROM user_ollama_server_profiles p
                      WHERE p.user_id = u.id
                        AND p.profile_name = 'default'
                  )
                """
            )
        )
        await conn.execute(
            text(
                """
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
                  AND COALESCE(TRIM(u.default_ollama_profile), '') = ''
                """
            )
        )
        await conn.execute(
            text(
                """
                UPDATE user_ollama_server_profiles p
                SET is_default = (p.profile_name = u.default_ollama_profile),
                    updated_at = NOW()
                FROM users u
                WHERE p.user_id = u.id
                  AND COALESCE(TRIM(u.default_ollama_profile), '') <> ''
                """
            )
        )

# Close database connections
async def close_db():
    await engine.dispose()
