-- Add default subtitle style preference columns for user settings
ALTER TABLE "users"
  ADD COLUMN IF NOT EXISTS "default_font_weight" INTEGER DEFAULT 600,
  ADD COLUMN IF NOT EXISTS "default_line_height" DOUBLE PRECISION DEFAULT 1.4,
  ADD COLUMN IF NOT EXISTS "default_letter_spacing" INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS "default_text_transform" VARCHAR(20) DEFAULT 'none',
  ADD COLUMN IF NOT EXISTS "default_text_align" VARCHAR(10) DEFAULT 'center',
  ADD COLUMN IF NOT EXISTS "default_stroke_color" VARCHAR(7) DEFAULT '#000000',
  ADD COLUMN IF NOT EXISTS "default_stroke_width" INTEGER DEFAULT 2,
  ADD COLUMN IF NOT EXISTS "default_shadow_color" VARCHAR(7) DEFAULT '#000000',
  ADD COLUMN IF NOT EXISTS "default_shadow_opacity" DOUBLE PRECISION DEFAULT 0.5,
  ADD COLUMN IF NOT EXISTS "default_shadow_blur" INTEGER DEFAULT 2,
  ADD COLUMN IF NOT EXISTS "default_shadow_offset_x" INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS "default_shadow_offset_y" INTEGER DEFAULT 2;
