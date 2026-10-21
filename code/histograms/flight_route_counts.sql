WITH all_routes AS (
    SELECT 'city' AS route_type, from_city AS origin, to_city AS destination,
           flight_number, raw_date AS flight_date
    FROM source.boarding_passes

    UNION ALL
    SELECT 'city', from_city, to_city, flight_number, flight_date
    FROM source.forum_flights

    UNION ALL
    SELECT 'airport', from_iata, to_iata, flight_number, raw_date
    FROM source.boarding_passes

    UNION ALL
    SELECT 'airport', "From", Dest, Flight, ArrivalDate
    FROM source.sirena

    UNION ALL
    SELECT 'airport', from_iata, to_iata, flight_number, flight_date
    FROM source.forum_flights

    UNION ALL
    SELECT 'airport', origin, destination, flight_number, flight_date
    FROM source.pointz_activities

    UNION ALL
    SELECT 'airport', from_iata, to_iata, flight_number, flight_date
    FROM source.skyteam_exchange
),
normalized AS (
    SELECT route_type,
           UPPER(TRIM(origin)) AS origin,
           UPPER(TRIM(destination)) AS destination,
           UPPER(REPLACE(TRIM(flight_number), ' ', '')) AS flight_number,
           TRY_CAST(flight_date AS DATE) AS flight_date
    FROM all_routes
),
unique_flights AS (
    SELECT DISTINCT route_type, origin, destination, flight_number, flight_date
    FROM normalized
    WHERE origin IS NOT NULL AND origin <> ''
      AND destination IS NOT NULL AND destination <> ''
      AND flight_number IS NOT NULL AND flight_number <> ''
      AND flight_date IS NOT NULL
)
SELECT route_type, origin, destination, COUNT(*) AS flight_count
FROM unique_flights
GROUP BY route_type, origin, destination
ORDER BY route_type, flight_count DESC, origin, destination;
