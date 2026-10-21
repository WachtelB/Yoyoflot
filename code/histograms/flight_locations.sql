WITH all_sources AS (
    SELECT FlightNumber AS flight_number, FlightDate AS flight_date,
           NULL AS from_city, Destination AS to_city,
           NULL AS from_airport, NULL AS to_airport
    FROM source.boarding_data

    UNION ALL
    SELECT flight_number, raw_date, from_city, to_city, from_iata, to_iata
    FROM source.boarding_passes

    UNION ALL
    SELECT Flight, DepartDate, NULL, NULL, "From", Dest
    FROM source.sirena

    UNION ALL
    SELECT flight_number, flight_date, from_city, to_city, from_iata, to_iata
    FROM source.forum_flights

    UNION ALL
    SELECT flight_number, flight_date, NULL, NULL, origin, destination
    FROM source.pointz_activities

    UNION ALL
    SELECT flight_number, flight_date, NULL, NULL, from_iata, to_iata
    FROM source.skyteam_exchange
),
normalized AS (
    SELECT
        UPPER(REPLACE(TRIM(flight_number), ' ', '')) AS flight_number,
        TRY_CAST(flight_date AS DATE) AS flight_date,
        UPPER(TRIM(from_city)) AS from_city,
        UPPER(TRIM(to_city)) AS to_city,
        UPPER(TRIM(from_airport)) AS from_airport,
        UPPER(TRIM(to_airport)) AS to_airport
    FROM all_sources
),
locations AS (
    SELECT flight_number, flight_date,
           'city' AS location_type, 'departure' AS direction, from_city AS location
    FROM normalized

    UNION ALL
    SELECT flight_number, flight_date, 'city', 'arrival', to_city
    FROM normalized

    UNION ALL
    SELECT flight_number, flight_date, 'airport', 'departure', from_airport
    FROM normalized

    UNION ALL
    SELECT flight_number, flight_date, 'airport', 'arrival', to_airport
    FROM normalized
)
SELECT DISTINCT flight_number, flight_date, location_type, direction, location
FROM locations
WHERE flight_number IS NOT NULL AND flight_number <> ''
  AND flight_date IS NOT NULL
  AND location IS NOT NULL AND location <> '';
