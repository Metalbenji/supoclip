ALTER TABLE "users"
ADD COLUMN IF NOT EXISTS "default_review_auto_select_strong_face_enabled" BOOLEAN DEFAULT false;

ALTER TABLE "users"
ADD COLUMN IF NOT EXISTS "default_review_auto_select_strong_face_min_score_percent" INTEGER DEFAULT 85;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'check_users_default_review_auto_select_strong_face_min_score_percent'
  ) THEN
    ALTER TABLE "users" DROP CONSTRAINT check_users_default_review_auto_select_strong_face_min_score_percent;
  END IF;
END $$;

ALTER TABLE "users"
ADD CONSTRAINT check_users_default_review_auto_select_strong_face_min_score_percent
CHECK (
  "default_review_auto_select_strong_face_min_score_percent" IS NULL
  OR "default_review_auto_select_strong_face_min_score_percent" BETWEEN 0 AND 100
);
