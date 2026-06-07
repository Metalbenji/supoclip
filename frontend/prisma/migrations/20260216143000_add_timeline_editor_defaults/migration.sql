-- Add user/task timeline-editor toggle defaults used by review UI.

ALTER TABLE "users"
ADD COLUMN IF NOT EXISTS "default_timeline_editor_enabled" BOOLEAN DEFAULT true;

ALTER TABLE "tasks"
ADD COLUMN IF NOT EXISTS "review_before_render_enabled" BOOLEAN NOT NULL DEFAULT true;

ALTER TABLE "tasks"
ADD COLUMN IF NOT EXISTS "timeline_editor_enabled" BOOLEAN NOT NULL DEFAULT true;
