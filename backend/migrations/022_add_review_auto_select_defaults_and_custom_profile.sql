ALTER TABLE users
ADD COLUMN IF NOT EXISTS default_review_auto_select_strong_face_enabled BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE users
ADD COLUMN IF NOT EXISTS default_review_auto_select_strong_face_min_score_percent INTEGER NOT NULL DEFAULT 85;

ALTER TABLE users DROP CONSTRAINT IF EXISTS check_users_default_processing_profile;
ALTER TABLE users
ADD CONSTRAINT check_users_default_processing_profile
CHECK (default_processing_profile IN ('fast_draft', 'balanced', 'best_quality', 'stream_layout', 'custom'));

ALTER TABLE tasks DROP CONSTRAINT IF EXISTS check_tasks_processing_profile;
ALTER TABLE tasks
ADD CONSTRAINT check_tasks_processing_profile
CHECK (processing_profile IN ('fast_draft', 'balanced', 'best_quality', 'stream_layout', 'custom'));

ALTER TABLE users DROP CONSTRAINT IF EXISTS check_users_default_review_auto_select_strong_face_min_score_percent;
ALTER TABLE users
ADD CONSTRAINT check_users_default_review_auto_select_strong_face_min_score_percent
CHECK (default_review_auto_select_strong_face_min_score_percent BETWEEN 0 AND 100);
