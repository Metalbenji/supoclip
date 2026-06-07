ALTER TABLE users
ADD COLUMN IF NOT EXISTS default_output_aspect_ratio VARCHAR(12) NOT NULL DEFAULT '9:16';

ALTER TABLE users DROP CONSTRAINT IF EXISTS check_users_default_output_aspect_ratio;
ALTER TABLE users
ADD CONSTRAINT check_users_default_output_aspect_ratio
CHECK (default_output_aspect_ratio IN ('auto', '1:1', '21:9', '16:9', '9:16', '4:3', '4:5', '5:4', '3:4', '3:2', '2:3'));
