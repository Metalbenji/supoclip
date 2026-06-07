-- Add default z.ai key routing mode preference for user-level settings.
ALTER TABLE "users"
ADD COLUMN IF NOT EXISTS "default_zai_key_routing_mode" VARCHAR(20) DEFAULT 'auto';
