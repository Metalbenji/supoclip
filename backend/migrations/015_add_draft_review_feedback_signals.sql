-- Persist review-feedback signals and adjusted review scores for draft clip ranking.

ALTER TABLE task_clip_drafts
ADD COLUMN IF NOT EXISTS review_score FLOAT NOT NULL DEFAULT 0;

ALTER TABLE task_clip_drafts
ADD COLUMN IF NOT EXISTS feedback_score_adjustment FLOAT NOT NULL DEFAULT 0;

ALTER TABLE task_clip_drafts
ADD COLUMN IF NOT EXISTS feedback_signals_json JSONB;

UPDATE task_clip_drafts
SET review_score = COALESCE(review_score, relevance_score),
    feedback_score_adjustment = COALESCE(feedback_score_adjustment, 0),
    feedback_signals_json = COALESCE(feedback_signals_json, '{}'::jsonb);

COMMENT ON COLUMN task_clip_drafts.review_score IS 'Adjusted review-time score derived from AI score plus user feedback signals.';
COMMENT ON COLUMN task_clip_drafts.feedback_score_adjustment IS 'Signed adjustment applied to the base AI score from review feedback.';
COMMENT ON COLUMN task_clip_drafts.feedback_signals_json IS 'Structured review-feedback signals such as timing edits, text edits, deselection, and manual creation.';
