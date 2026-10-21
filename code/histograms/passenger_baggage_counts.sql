WITH all_records AS (
    SELECT PassengerDocument AS document, TicketNumber AS ticket,
           UPPER(TRIM(Baggage)) IN ('REGISTERED', 'TRANSIT', 'DELAYED') AS has_baggage,
           NULLIF(CONCAT_WS(' ', NULLIF(TRIM(PassengerFirstName), ''),
                                NULLIF(TRIM(PassengerSecondName), ''),
                                NULLIF(TRIM(PassengerLastName), '')), '') AS full_name
    FROM source.boarding_data

    UNION ALL
    SELECT TravelDoc, "e-Ticket", UPPER(TRIM(Baggage)) IN ('1PC', '2PC'),
           NULLIF(TRIM(PaxName), '')
    FROM source.sirena
),
normalized AS (
    SELECT UPPER(REGEXP_REPLACE(TRIM(document), '\s+', '', 'g')) AS document,
           UPPER(REGEXP_REPLACE(TRIM(ticket), '\s+', '', 'g')) AS ticket,
           has_baggage, full_name
    FROM all_records
),
passenger_tickets AS (
    SELECT document,
           CASE WHEN ticket IN ('', 'NOTPRESENTED', 'N/A', 'NONE', 'NULL', '-')
                THEN NULL ELSE ticket END AS ticket,
           has_baggage, full_name
    FROM normalized
    WHERE document IS NOT NULL
      AND document NOT IN ('', 'NOTPRESENTED', 'N/A', 'NONE', 'NULL', '-')
)
SELECT document,
       COUNT(DISTINCT ticket) FILTER (WHERE has_baggage) AS baggage_flight_count,
       STRING_AGG(DISTINCT full_name, ' / ' ORDER BY full_name) AS full_name
FROM passenger_tickets
GROUP BY document
ORDER BY baggage_flight_count DESC, document;
