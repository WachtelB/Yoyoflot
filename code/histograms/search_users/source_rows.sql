CREATE OR REPLACE TEMP TABLE search_source_rows AS
SELECT norm_id(b.PassengerDocument) AS document, 'boarding_data' AS source_table,
       CAST(TO_JSON(b) AS VARCHAR) AS row_json
FROM source.boarding_data b WHERE norm_id(b.PassengerDocument) IS NOT NULL
UNION ALL
SELECT norm_id(s.TravelDoc), 'sirena', CAST(TO_JSON(s) AS VARCHAR)
FROM source.sirena s WHERE norm_id(s.TravelDoc) IS NOT NULL
UNION ALL
SELECT owners.document, 'boarding_passes', CAST(TO_JSON(bp) AS VARCHAR)
FROM source.boarding_passes bp
JOIN ticket_owners owners ON norm_id(bp.e_ticket) = owners.ticket
WHERE owners.owner_count = 1
UNION ALL
SELECT pc.document, 'forum_loyalty', CAST(TO_JSON(f) AS VARCHAR)
FROM source.forum_loyalty f
JOIN passenger_cards pc ON pc.basis = 'forum:' || CAST(f.profile_id AS VARCHAR)
                      AND pc.card = card_key(f.program, f.number)
UNION ALL
SELECT pc.document, 'pointz_activities', CAST(TO_JSON(p) AS VARCHAR)
FROM source.pointz_activities p
JOIN passenger_cards pc ON pc.basis = 'pointz:' || CAST(p.uid AS VARCHAR)
 AND pc.card = card_key(CASE UPPER(TRIM(p.bonus_program))
     WHEN 'AEROFLOT BONUS' THEN 'SU' WHEN 'DELTA SKYMILES' THEN 'DT'
     WHEN 'FLYING BLUE' THEN 'FB' WHEN 'KOREAN AIR SKYPASS' THEN 'KE'
 END, p.card_number);
