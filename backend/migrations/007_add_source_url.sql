-- Add source URL field to retain original input URL for task display.
ALTER TABLE sources
ADD COLUMN IF NOT EXISTS url TEXT;
