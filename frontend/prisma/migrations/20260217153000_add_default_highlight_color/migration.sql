ALTER TABLE users
ADD COLUMN IF NOT EXISTS default_highlight_color VARCHAR(7) DEFAULT '#FDE047';

UPDATE users
SET default_highlight_color = '#FDE047'
WHERE default_highlight_color IS NULL;
