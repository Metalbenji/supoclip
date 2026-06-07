-- Persist optional AI clip-selection focus tags selected at task creation.
ALTER TABLE tasks
ADD COLUMN IF NOT EXISTS ai_focus_tags JSONB;

COMMENT ON COLUMN tasks.ai_focus_tags IS 'Optional ordered list of AI focus tags used to bias transcript clip selection.';
