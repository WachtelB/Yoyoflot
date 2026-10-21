WITH flights AS (
    SELECT
        COALESCE(
            NULLIF(TRIM(raw_name), ''),
            NULLIF(CONCAT_WS(' ',
                NULLIF(TRIM(PassengerFirstName), ''),
                NULLIF(TRIM(PassengerSecondName), ''),
                NULLIF(TRIM(PassengerLastName), '')
            ), '')
        ) AS passenger_name,
        COALESCE(
            TRY_CAST(raw_date AS DATE),
            TRY_CAST(FlightDate AS DATE)
        ) AS flight_date,
        COALESCE(
            NULLIF(TRIM(flight_number), ''),
            NULLIF(TRIM(FlightNumber), '')
        ) AS flight,
        COALESCE(
            NULLIF(TRIM(to_city), ''),
            NULLIF(TRIM(Destination), '')
        ) AS destination,
        NULLIF(TRIM(Baggage), '') AS baggage
    FROM source."boarding_data + boarding_passes"
)
SELECT passenger_name, flight_date, flight, destination, baggage
FROM flights
ORDER BY passenger_name NULLS LAST, flight_date NULLS LAST, flight, destination;
