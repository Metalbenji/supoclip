-- Persist draft-level framing analysis and simple framing overrides for review-time control.

ALTER TABLE task_clip_drafts
ADD COLUMN IF NOT EXISTS framing_metadata_json JSONB;

ALTER TABLE task_clip_drafts
ADD COLUMN IF NOT EXISTS framing_mode_override VARCHAR(32) NOT NULL DEFAULT 'auto';

UPDATE task_clip_drafts
SET framing_metadata_json = COALESCE(framing_metadata_json, '{}'::jsonb),
    framing_mode_override = COALESCE(NULLIF(TRIM(framing_mode_override), ''), 'auto');

COMMENT ON COLUMN task_clip_drafts.framing_metadata_json IS 'Structured face/framing analysis used for review-time framing guidance and crop defaults.';
COMMENT ON COLUMN task_clip_drafts.framing_mode_override IS 'Per-draft framing override: auto, prefer_face, or disable_face_crop.';
