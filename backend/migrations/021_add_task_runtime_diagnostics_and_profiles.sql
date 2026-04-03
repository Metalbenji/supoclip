ALTER TABLE users
ADD COLUMN IF NOT EXISTS default_processing_profile VARCHAR(32) NOT NULL DEFAULT 'balanced';

ALTER TABLE tasks
ADD COLUMN IF NOT EXISTS processing_profile VARCHAR(32) NOT NULL DEFAULT 'balanced',
ADD COLUMN IF NOT EXISTS runtime_info_json JSONB,
ADD COLUMN IF NOT EXISTS failure_code VARCHAR(40),
ADD COLUMN IF NOT EXISTS failure_hint TEXT,
ADD COLUMN IF NOT EXISTS stage_checkpoint VARCHAR(32) NOT NULL DEFAULT 'queued',
ADD COLUMN IF NOT EXISTS retryable_from_stages JSONB;

UPDATE users
SET default_processing_profile = COALESCE(NULLIF(TRIM(default_processing_profile), ''), 'balanced');

UPDATE tasks
SET
  processing_profile = COALESCE(NULLIF(TRIM(processing_profile), ''), 'balanced'),
  stage_checkpoint = COALESCE(NULLIF(TRIM(stage_checkpoint), ''), 'queued');

ALTER TABLE users DROP CONSTRAINT IF EXISTS check_users_default_processing_profile;
ALTER TABLE users
ADD CONSTRAINT check_users_default_processing_profile
CHECK (default_processing_profile IN ('fast_draft', 'balanced', 'best_quality', 'stream_layout'));

ALTER TABLE tasks DROP CONSTRAINT IF EXISTS check_tasks_processing_profile;
ALTER TABLE tasks
ADD CONSTRAINT check_tasks_processing_profile
CHECK (processing_profile IN ('fast_draft', 'balanced', 'best_quality', 'stream_layout'));

ALTER TABLE tasks DROP CONSTRAINT IF EXISTS check_tasks_stage_checkpoint;
ALTER TABLE tasks
ADD CONSTRAINT check_tasks_stage_checkpoint
CHECK (stage_checkpoint IN ('queued', 'started', 'downloaded', 'transcribed', 'analyzed', 'review_approved', 'completed', 'failed'));
