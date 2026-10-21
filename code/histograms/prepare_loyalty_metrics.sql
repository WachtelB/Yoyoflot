CREATE OR REPLACE TEMP MACRO card_key(program, number) AS (
    CASE
      WHEN norm_id(program) IS NULL THEN NULL
      WHEN REGEXP_FULL_MATCH(norm_id(number), '[0-9]+')
        THEN norm_id(program) || norm_id(number)
      WHEN STARTS_WITH(norm_id(number), norm_id(program))
        AND REGEXP_FULL_MATCH(SUBSTR(norm_id(number), LENGTH(norm_id(program)) + 1), '[0-9]+')
        THEN norm_id(number)
    END
);

CREATE OR REPLACE TEMP TABLE direct_cards AS
SELECT DISTINCT norm_id(TravelDoc) AS document,
       REGEXP_REPLACE(SUBSTR(match, 4), '\s+', '', 'g') AS card
FROM source.sirena,
UNNEST(REGEXP_EXTRACT_ALL(UPPER(PaxAdditionalInfo), 'FF#[A-Z0-9]{2}\s+[0-9]+\b')) AS found(match)
WHERE norm_id(TravelDoc) IS NOT NULL;

CREATE OR REPLACE TEMP TABLE profile_cards AS
SELECT DISTINCT 'forum:' || CAST(profile_id AS VARCHAR) AS profile,
       card_key(program, number) AS card
FROM source.forum_loyalty WHERE profile_id IS NOT NULL
UNION
SELECT 'pointz:' || CAST(uid AS VARCHAR),
       card_key(CASE UPPER(TRIM(bonus_program))
         WHEN 'AEROFLOT BONUS' THEN 'SU'
         WHEN 'DELTA SKYMILES' THEN 'DT'
         WHEN 'FLYING BLUE' THEN 'FB'
         WHEN 'KOREAN AIR SKYPASS' THEN 'KE'
       END, card_number)
FROM source.pointz_activities WHERE uid IS NOT NULL;

CREATE OR REPLACE TEMP TABLE direct_card_owners AS
SELECT card, MIN(document) AS document, COUNT(DISTINCT document) AS owner_count
FROM direct_cards GROUP BY card;

CREATE OR REPLACE TEMP TABLE profile_owners AS
SELECT p.profile, MIN(d.document) AS document,
       COUNT(DISTINCT d.document) AS owner_count, MAX(d.owner_count) AS max_card_owners
FROM profile_cards p JOIN direct_card_owners d USING (card)
GROUP BY p.profile;

CREATE OR REPLACE TEMP TABLE card_candidates AS
SELECT document, card, 'sirena' AS basis FROM direct_cards
UNION ALL
SELECT owners.document, p.card, p.profile
FROM profile_owners owners JOIN profile_cards p USING (profile)
WHERE owners.owner_count = 1 AND owners.max_card_owners = 1 AND p.card IS NOT NULL;

CREATE OR REPLACE TEMP TABLE passenger_cards AS
WITH owners AS (
    SELECT card, COUNT(DISTINCT document) AS owner_count FROM card_candidates GROUP BY card
)
SELECT DISTINCT c.document, c.card, c.basis
FROM card_candidates c JOIN owners USING (card)
WHERE c.basis = 'sirena' OR owners.owner_count = 1;
