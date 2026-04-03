ALTER TABLE users
ADD COLUMN IF NOT EXISTS default_fallback_crop_position VARCHAR(20) NOT NULL DEFAULT 'center';

UPDATE users
SET
    default_framing_mode = CASE
        WHEN COALESCE(NULLIF(TRIM(default_framing_mode), ''), 'auto') = 'disable_face_crop'
            THEN 'fixed_position'
        ELSE COALESCE(NULLIF(TRIM(default_framing_mode), ''), 'auto')
    END,
    default_face_detection_mode = CASE
        WHEN COALESCE(NULLIF(TRIM(default_face_detection_mode), ''), 'balanced') = 'center_only'
            THEN 'balanced'
        ELSE COALESCE(NULLIF(TRIM(default_face_detection_mode), ''), 'balanced')
    END,
    default_fallback_crop_position = COALESCE(NULLIF(TRIM(default_fallback_crop_position), ''), 'center');

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'check_users_default_framing_mode'
    ) THEN
        ALTER TABLE users DROP CONSTRAINT check_users_default_framing_mode;
    END IF;
    ALTER TABLE users
    ADD CONSTRAINT check_users_default_framing_mode
    CHECK (default_framing_mode IN ('auto', 'prefer_face', 'fixed_position'));
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'check_users_default_face_detection_mode'
    ) THEN
        ALTER TABLE users DROP CONSTRAINT check_users_default_face_detection_mode;
    END IF;
    ALTER TABLE users
    ADD CONSTRAINT check_users_default_face_detection_mode
    CHECK (default_face_detection_mode IN ('balanced', 'more_faces'));
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'check_users_default_fallback_crop_position'
    ) THEN
        ALTER TABLE users DROP CONSTRAINT check_users_default_fallback_crop_position;
    END IF;
    ALTER TABLE users
    ADD CONSTRAINT check_users_default_fallback_crop_position
    CHECK (default_fallback_crop_position IN ('center', 'left_center', 'right_center'));
END $$;
