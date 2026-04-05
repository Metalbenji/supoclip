CREATE TABLE IF NOT EXISTS saved_workflows (
  id VARCHAR(36) PRIMARY KEY,
  user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name VARCHAR(120) NOT NULL,
  review_before_render_enabled BOOLEAN NOT NULL DEFAULT true,
  timeline_editor_enabled BOOLEAN NOT NULL DEFAULT true,
  transitions_enabled BOOLEAN NOT NULL DEFAULT false,
  transcription_provider VARCHAR(20) NOT NULL DEFAULT 'local',
  whisper_model_size VARCHAR(20) NOT NULL DEFAULT 'medium',
  default_framing_mode VARCHAR(32) NOT NULL DEFAULT 'auto',
  face_detection_mode VARCHAR(20) NOT NULL DEFAULT 'balanced',
  fallback_crop_position VARCHAR(20) NOT NULL DEFAULT 'center',
  face_anchor_profile VARCHAR(24) NOT NULL DEFAULT 'auto',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_saved_workflows_user_id ON saved_workflows(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_saved_workflows_user_name_lower ON saved_workflows(user_id, LOWER(name));

ALTER TABLE users
ADD COLUMN IF NOT EXISTS default_workflow_source VARCHAR(16) NOT NULL DEFAULT 'built_in';

ALTER TABLE users
ADD COLUMN IF NOT EXISTS default_saved_workflow_id VARCHAR(36);

ALTER TABLE tasks
ADD COLUMN IF NOT EXISTS workflow_source VARCHAR(16) NOT NULL DEFAULT 'built_in';

ALTER TABLE tasks
ADD COLUMN IF NOT EXISTS saved_workflow_id VARCHAR(36);

ALTER TABLE tasks
ADD COLUMN IF NOT EXISTS workflow_name_snapshot VARCHAR(120);

ALTER TABLE users DROP CONSTRAINT IF EXISTS check_users_default_workflow_source;
ALTER TABLE users
ADD CONSTRAINT check_users_default_workflow_source
CHECK (default_workflow_source IN ('built_in', 'saved', 'custom'));

ALTER TABLE tasks DROP CONSTRAINT IF EXISTS check_tasks_workflow_source;
ALTER TABLE tasks
ADD CONSTRAINT check_tasks_workflow_source
CHECK (workflow_source IN ('built_in', 'saved', 'custom'));

ALTER TABLE saved_workflows DROP CONSTRAINT IF EXISTS check_saved_workflows_transcription_provider;
ALTER TABLE saved_workflows
ADD CONSTRAINT check_saved_workflows_transcription_provider
CHECK (transcription_provider IN ('local', 'assemblyai'));

ALTER TABLE saved_workflows DROP CONSTRAINT IF EXISTS check_saved_workflows_whisper_model_size;
ALTER TABLE saved_workflows
ADD CONSTRAINT check_saved_workflows_whisper_model_size
CHECK (whisper_model_size IN ('tiny', 'base', 'small', 'medium', 'large', 'turbo'));

ALTER TABLE saved_workflows DROP CONSTRAINT IF EXISTS check_saved_workflows_default_framing_mode;
ALTER TABLE saved_workflows
ADD CONSTRAINT check_saved_workflows_default_framing_mode
CHECK (default_framing_mode IN ('auto', 'prefer_face', 'fixed_position'));

ALTER TABLE saved_workflows DROP CONSTRAINT IF EXISTS check_saved_workflows_face_detection_mode;
ALTER TABLE saved_workflows
ADD CONSTRAINT check_saved_workflows_face_detection_mode
CHECK (face_detection_mode IN ('balanced', 'more_faces'));

ALTER TABLE saved_workflows DROP CONSTRAINT IF EXISTS check_saved_workflows_fallback_crop_position;
ALTER TABLE saved_workflows
ADD CONSTRAINT check_saved_workflows_fallback_crop_position
CHECK (fallback_crop_position IN ('center', 'left_center', 'right_center'));

ALTER TABLE saved_workflows DROP CONSTRAINT IF EXISTS check_saved_workflows_face_anchor_profile;
ALTER TABLE saved_workflows
ADD CONSTRAINT check_saved_workflows_face_anchor_profile
CHECK (face_anchor_profile IN ('auto', 'left_only', 'left_or_center', 'center_only', 'right_or_center', 'right_only'));

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'users_default_saved_workflow_id_fkey'
  ) THEN
    ALTER TABLE users
    ADD CONSTRAINT users_default_saved_workflow_id_fkey
    FOREIGN KEY (default_saved_workflow_id) REFERENCES saved_workflows(id) ON DELETE SET NULL;
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'tasks_saved_workflow_id_fkey'
  ) THEN
    ALTER TABLE tasks
    ADD CONSTRAINT tasks_saved_workflow_id_fkey
    FOREIGN KEY (saved_workflow_id) REFERENCES saved_workflows(id) ON DELETE SET NULL;
  END IF;
END $$;
