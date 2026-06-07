-- Add user-level default toggle for review-before-render.

ALTER TABLE users
ADD COLUMN IF NOT EXISTS default_review_before_render_enabled BOOLEAN NOT NULL DEFAULT true;

COMMENT ON COLUMN users.default_review_before_render_enabled IS 'Default setting for whether new tasks pause at review-before-render stage.';
