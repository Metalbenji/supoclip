-- Add interactive timeline editor controls for review-stage draft clips.

ALTER TABLE users
ADD COLUMN IF NOT EXISTS default_timeline_editor_enabled BOOLEAN NOT NULL DEFAULT true;

ALTER TABLE tasks
ADD COLUMN IF NOT EXISTS timeline_editor_enabled BOOLEAN NOT NULL DEFAULT true;

ALTER TABLE task_clip_drafts
ADD COLUMN IF NOT EXISTS original_start_time VARCHAR(20);

ALTER TABLE task_clip_drafts
ADD COLUMN IF NOT EXISTS original_end_time VARCHAR(20);

ALTER TABLE task_clip_drafts
ADD COLUMN IF NOT EXISTS original_duration FLOAT;

ALTER TABLE task_clip_drafts
ADD COLUMN IF NOT EXISTS created_by_user BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE task_clip_drafts
ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT false;

UPDATE task_clip_drafts
SET original_start_time = COALESCE(original_start_time, start_time),
    original_end_time = COALESCE(original_end_time, end_time),
    original_duration = COALESCE(original_duration, duration);

ALTER TABLE task_clip_drafts
ALTER COLUMN original_start_time SET NOT NULL;

ALTER TABLE task_clip_drafts
ALTER COLUMN original_end_time SET NOT NULL;

ALTER TABLE task_clip_drafts
ALTER COLUMN original_duration SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_task_clip_drafts_active
    ON task_clip_drafts(task_id, is_deleted);

COMMENT ON COLUMN users.default_timeline_editor_enabled IS 'Default setting for enabling interactive timeline editor during review.';
COMMENT ON COLUMN tasks.timeline_editor_enabled IS 'Per-task override for interactive timeline editor visibility in review stage.';
COMMENT ON COLUMN task_clip_drafts.original_start_time IS 'Initial AI/generated clip start time used for restore.';
COMMENT ON COLUMN task_clip_drafts.original_end_time IS 'Initial AI/generated clip end time used for restore.';
COMMENT ON COLUMN task_clip_drafts.original_duration IS 'Initial AI/generated clip duration used for restore.';
COMMENT ON COLUMN task_clip_drafts.created_by_user IS 'True when draft clip was added manually by user during review.';
COMMENT ON COLUMN task_clip_drafts.is_deleted IS 'Soft-delete marker used to support draft restore workflow.';
