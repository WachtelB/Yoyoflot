SELECT
    b.PassengerDocument AS boarding_document,
    s.TravelDoc AS sirena_document,
    b.PassengerFirstName AS first_name,
    b.PassengerLastName AS last_name,
    b.FlightDate AS boarding_date,
    b.FlightNumber AS boarding_flight,
    s.DepartDate AS sirena_date,
    s.Flight AS sirena_flight,
    b.Baggage AS boarding_baggage,
    s.Baggage AS sirena_baggage,
    b.source_row AS boarding_source_row,
    s.source_row AS sirena_source_row
FROM source.boarding_data AS b
JOIN source.sirena AS s
    ON REPLACE(TRIM(b.PassengerDocument), ' ', '')
     = REPLACE(TRIM(s.TravelDoc), ' ', '')
    AND UPPER(TRIM(b.FlightNumber)) = UPPER(TRIM(s.Flight))
    AND TRY_CAST(b.FlightDate AS DATE) = TRY_CAST(s.DepartDate AS DATE)
WHERE
    REPLACE(TRIM(b.PassengerDocument), ' ', '') <> ''
    AND TRIM(b.FlightNumber) <> ''
    AND (
        (
            TRIM(b.Baggage) = 'None'
            AND TRIM(s.Baggage) IN ('1PC', '2PC')
        )
    );
