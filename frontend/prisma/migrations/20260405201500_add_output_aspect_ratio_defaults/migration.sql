ALTER TABLE "users"
ADD COLUMN IF NOT EXISTS "default_output_aspect_ratio" VARCHAR(12) DEFAULT '9:16';

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'check_users_default_output_aspect_ratio'
  ) THEN
    ALTER TABLE "users" DROP CONSTRAINT check_users_default_output_aspect_ratio;
  END IF;
END $$;

ALTER TABLE "users"
ADD CONSTRAINT check_users_default_output_aspect_ratio
CHECK ("default_output_aspect_ratio" IN ('auto', '1:1', '21:9', '16:9', '9:16', '4:3', '4:5', '5:4', '3:4', '3:2', '2:3'));
