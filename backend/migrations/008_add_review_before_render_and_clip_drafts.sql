-- Add optional review-before-render workflow support.

ALTER TABLE tasks
ADD COLUMN IF NOT EXISTS review_before_render_enabled BOOLEAN NOT NULL DEFAULT true;

ALTER TABLE tasks
ADD COLUMN IF NOT EXISTS transitions_enabled BOOLEAN NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS task_clip_drafts (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    task_id VARCHAR(36) NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    clip_order INTEGER NOT NULL,
    start_time VARCHAR(20) NOT NULL,
    end_time VARCHAR(20) NOT NULL,
    duration FLOAT NOT NULL,
    original_text TEXT,
    edited_text TEXT,
    relevance_score FLOAT NOT NULL,
    reasoning TEXT,
    is_selected BOOLEAN NOT NULL DEFAULT true,
    edited_word_timings_json JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_task_clip_drafts_task_id ON task_clip_drafts(task_id);
CREATE INDEX IF NOT EXISTS idx_task_clip_drafts_clip_order ON task_clip_drafts(clip_order);
CREATE UNIQUE INDEX IF NOT EXISTS uq_task_clip_drafts_task_order ON task_clip_drafts(task_id, clip_order);

COMMENT ON COLUMN tasks.review_before_render_enabled IS 'When true, task stops after analysis and requires user review before rendering.';
COMMENT ON COLUMN task_clip_drafts.edited_word_timings_json IS 'Aligned per-word subtitle timings for edited text, stored as JSON.';
