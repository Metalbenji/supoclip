-- Add user-level default for review-before-render create option.

ALTER TABLE "users"
ADD COLUMN IF NOT EXISTS "default_review_before_render_enabled" BOOLEAN DEFAULT true;
