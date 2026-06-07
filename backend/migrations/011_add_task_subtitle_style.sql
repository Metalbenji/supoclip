-- Persist per-task subtitle style so review/finalize rendering keeps stroke/shadow settings.

ALTER TABLE tasks
ADD COLUMN IF NOT EXISTS subtitle_style JSONB;

COMMENT ON COLUMN tasks.subtitle_style IS 'Normalized subtitle style options captured at task creation.';
