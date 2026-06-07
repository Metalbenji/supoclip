-- Add dim_unhighlighted setting for karaoke subtitle opacity control.
-- When false, unhighlighted words are rendered at full opacity instead of dimmed to 52%.
ALTER TABLE users ADD COLUMN IF NOT EXISTS default_dim_unhighlighted BOOLEAN NOT NULL DEFAULT true;
