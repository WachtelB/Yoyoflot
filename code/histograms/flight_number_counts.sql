WITH all_sources AS (
    SELECT 'boarding_passes' AS source_name, flight_number,
           raw_date AS flight_date, flight_time
    FROM source.boarding_passes
    UNION ALL
    SELECT 'sirena', Flight, DepartDate, DepartTime
    FROM source.sirena

    UNION ALL
    SELECT 'boarding_data', FlightNumber, FlightDate, NULL
    FROM source.boarding_data
    UNION ALL
    SELECT 'forum_flights', flight_number, flight_date, NULL
    FROM source.forum_flights
    UNION ALL
    SELECT 'pointz_activities', flight_number, flight_date, NULL
    FROM source.pointz_activities
    UNION ALL
    SELECT 'skyteam_exchange', flight_number, flight_date, NULL
    FROM source.skyteam_exchange
),
normalized AS (
    SELECT source_name,
           UPPER(REGEXP_REPLACE(TRIM(flight_number), '\s+', '', 'g')) AS flight_number,
           TRY_CAST(flight_date AS DATE) AS flight_date,
           TRY_CAST(flight_time AS TIME) AS flight_time
    FROM all_sources
),
valid_rows AS (
    SELECT * FROM normalized
    WHERE flight_number IS NOT NULL AND flight_number <> ''
      AND flight_date IS NOT NULL
),
daily_total AS (
    SELECT flight_number, flight_date,
           GREATEST(COUNT(DISTINCT flight_time), 1) AS flight_count
    FROM valid_rows
    GROUP BY flight_number, flight_date
),
totals AS (
    SELECT flight_number, SUM(flight_count) AS total_flights
    FROM daily_total
    GROUP BY flight_number
),
daily_by_source AS (
    SELECT source_name, flight_number, flight_date,
           GREATEST(COUNT(DISTINCT flight_time), 1) AS flight_count
    FROM valid_rows
    GROUP BY source_name, flight_number, flight_date
),
by_source AS (
    SELECT flight_number,
           SUM(CASE WHEN source_name = 'boarding_data' THEN flight_count ELSE 0 END) AS boarding_data,
           SUM(CASE WHEN source_name = 'boarding_passes' THEN flight_count ELSE 0 END) AS boarding_passes,
           SUM(CASE WHEN source_name = 'sirena' THEN flight_count ELSE 0 END) AS sirena,
           SUM(CASE WHEN source_name = 'forum_flights' THEN flight_count ELSE 0 END) AS forum_flights,
           SUM(CASE WHEN source_name = 'pointz_activities' THEN flight_count ELSE 0 END) AS pointz_activities,
           SUM(CASE WHEN source_name = 'skyteam_exchange' THEN flight_count ELSE 0 END) AS skyteam_exchange
    FROM daily_by_source
    GROUP BY flight_number
)
SELECT totals.*, by_source.* EXCLUDE (flight_number)
FROM totals JOIN by_source USING (flight_number)
ORDER BY total_flights DESC, flight_number;
