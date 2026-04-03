ALTER TABLE "users"
ADD COLUMN IF NOT EXISTS "default_processing_profile" VARCHAR(32) DEFAULT 'balanced';
