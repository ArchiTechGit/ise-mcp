-- Migration 013: Backfill NULL is_active flags on seeded guidance rows
-- Version: 013
-- Date: 2026-08-22
--
-- Root cause: the SQLAlchemy models declare is_active with a *client-side*
-- default (Column(Boolean, default=True)), so the table that create_all()
-- builds has no server DEFAULT. Migrations 004 and 006 inserted their seed rows
-- without naming the column, leaving is_active NULL rather than TRUE.
--
-- Every read path filters on `is_active == True`, and NULL does not satisfy
-- that. The effect was silent: the rows existed, the queries returned nothing,
-- and no error was raised anywhere.
--
--   system_prompt_sections  -> generate_system_prompt() emitted no guidance
--                              at all, only workflows
--   api_guidance            -> absent from the generated prompt
--   category_guidance       -> absent from the prompt and the web UI
--   tool_profiles           -> hidden from the web UI profile list,
--                              including "Full Access"
--
-- Those migrations now set is_active explicitly. This repairs deployments that
-- had already applied them.

UPDATE system_prompt_sections      SET is_active = TRUE WHERE is_active IS NULL;
UPDATE api_guidance                SET is_active = TRUE WHERE is_active IS NULL;
UPDATE category_guidance           SET is_active = TRUE WHERE is_active IS NULL;
UPDATE tool_profiles               SET is_active = TRUE WHERE is_active IS NULL;
UPDATE workflows                   SET is_active = TRUE WHERE is_active IS NULL;
UPDATE use_cases                   SET is_active = TRUE WHERE is_active IS NULL;
UPDATE tool_description_overrides  SET is_active = TRUE WHERE is_active IS NULL;

-- Give the columns a server-side default so a future raw INSERT that omits
-- them cannot reintroduce the same silent failure.
ALTER TABLE system_prompt_sections     ALTER COLUMN is_active SET DEFAULT TRUE;
ALTER TABLE api_guidance               ALTER COLUMN is_active SET DEFAULT TRUE;
ALTER TABLE category_guidance          ALTER COLUMN is_active SET DEFAULT TRUE;
ALTER TABLE tool_profiles              ALTER COLUMN is_active SET DEFAULT TRUE;
ALTER TABLE workflows                  ALTER COLUMN is_active SET DEFAULT TRUE;
ALTER TABLE use_cases                  ALTER COLUMN is_active SET DEFAULT TRUE;
ALTER TABLE tool_description_overrides ALTER COLUMN is_active SET DEFAULT TRUE;
