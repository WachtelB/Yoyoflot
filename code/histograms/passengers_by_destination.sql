WITH forum_people AS (
    SELECT profile_id,
        COALESCE(
            NULLIF(CONCAT_WS(' ', NULLIF(TRIM(raw_first_name), ''),
                                 NULLIF(TRIM(raw_last_name), '')), ''),
            NULLIF(TRIM(nickname), '')
        ) AS passenger_name
    FROM source.forum_users
),
card_candidates AS (
    SELECT UPPER(REPLACE(TRIM(card_number), ' ', '')) AS card_key,
        UPPER(NULLIF(CONCAT_WS(' ', NULLIF(TRIM(raw_first_name), ''),
                                   NULLIF(TRIM(raw_last_name), '')), '')) AS passenger_name
    FROM source.pointz_activities

    UNION ALL
    SELECT UPPER(REPLACE(TRIM(l.program) || TRIM(l.number), ' ', '')),
           UPPER(p.passenger_name)
    FROM source.forum_loyalty AS l
    JOIN forum_people AS p ON l.profile_id = p.profile_id
    WHERE NULLIF(TRIM(l.program), '') IS NOT NULL
      AND NULLIF(TRIM(l.number), '') IS NOT NULL
),
card_people AS (
    SELECT card_key,
        CASE WHEN COUNT(DISTINCT passenger_name) = 1
             THEN MIN(passenger_name) END AS passenger_name
    FROM card_candidates
    WHERE card_key IS NOT NULL AND card_key <> ''
      AND passenger_name IS NOT NULL
    GROUP BY card_key
),
all_passengers AS (
    SELECT FlightNumber AS flight_number, FlightDate AS flight_date,
           Destination AS to_city, NULL AS to_airport,
           NULLIF(CONCAT_WS(' ', NULLIF(TRIM(PassengerFirstName), ''),
                                NULLIF(TRIM(PassengerSecondName), ''),
                                NULLIF(TRIM(PassengerLastName), '')), '') AS passenger_name,
           'boarding_data' AS source_name, 'имя в записи' AS name_basis
    FROM source.boarding_data

    UNION ALL
    SELECT flight_number, raw_date, to_city, to_iata, raw_name,
           'boarding_passes', 'имя в записи'
    FROM source.boarding_passes

    UNION ALL
    SELECT Flight, DepartDate, NULL, Dest, PaxName, 'sirena', 'имя в записи'
    FROM source.sirena

    UNION ALL
    SELECT f.flight_number, f.flight_date, f.to_city, f.to_iata,
           COALESCE(p.passenger_name, NULLIF(TRIM(f.nickname), '')),
           'forum_flights', 'имя или ник профиля форума'
    FROM source.forum_flights AS f
    LEFT JOIN forum_people AS p ON f.profile_id = p.profile_id

    UNION ALL
    SELECT flight_number, flight_date, NULL, destination,
           NULLIF(CONCAT_WS(' ', NULLIF(TRIM(raw_first_name), ''),
                                NULLIF(TRIM(raw_last_name), '')), ''),
           'pointz_activities', 'имя в записи'
    FROM source.pointz_activities

    UNION ALL
    SELECT s.flight_number, s.flight_date, NULL, s.to_iata, p.passenger_name,
           'skyteam_exchange', 'имя по карте лояльности'
    FROM source.skyteam_exchange AS s
    LEFT JOIN card_people AS p
        ON UPPER(REPLACE(TRIM(s.norm_ff_card), ' ', '')) = p.card_key
),
normalized AS (
    SELECT UPPER(REPLACE(TRIM(flight_number), ' ', '')) AS flight_number,
           TRY_CAST(flight_date AS DATE) AS flight_date,
           UPPER(TRIM(to_city)) AS to_city,
           UPPER(TRIM(to_airport)) AS to_airport,
           NULLIF(TRIM(passenger_name), '') AS passenger_name,
           source_name, name_basis
    FROM all_passengers
),
destinations AS (
    SELECT 'city' AS location_type, to_city AS location,
           flight_number, flight_date, passenger_name, source_name, name_basis
    FROM normalized
    UNION ALL
    SELECT 'airport', to_airport,
           flight_number, flight_date, passenger_name, source_name, name_basis
    FROM normalized
)
SELECT DISTINCT d.location_type, d.location, d.flight_number, d.flight_date,
       d.passenger_name, d.source_name,
       CASE WHEN d.passenger_name IS NULL THEN 'имя не найдено'
            ELSE d.name_basis END AS name_basis
FROM destinations AS d
JOIN selected_destinations AS s
    ON d.location_type = s.location_type AND d.location = s.location
WHERE d.flight_number IS NOT NULL AND d.flight_number <> ''
  AND d.flight_date IS NOT NULL
ORDER BY d.location_type, d.location, d.flight_date, d.flight_number,
         d.passenger_name NULLS LAST, d.source_name;
