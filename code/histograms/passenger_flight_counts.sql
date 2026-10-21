WITH all_records AS (
    SELECT PassengerDocument AS document, TicketNumber AS ticket,
           NULLIF(CONCAT_WS(' ', NULLIF(TRIM(PassengerFirstName), ''),
                                NULLIF(TRIM(PassengerSecondName), ''),
                                NULLIF(TRIM(PassengerLastName), '')), '') AS full_name
    FROM source.boarding_data

    UNION ALL
    SELECT TravelDoc, "e-Ticket", NULLIF(TRIM(PaxName), '')
    FROM source.sirena
),
normalized AS (
    SELECT
        UPPER(REGEXP_REPLACE(TRIM(document), '\s+', '', 'g')) AS document,
        UPPER(REGEXP_REPLACE(TRIM(ticket), '\s+', '', 'g')) AS ticket,
        full_name
    FROM all_records
),
passenger_tickets AS (
    SELECT document,
        CASE
            WHEN ticket IN ('', 'NOTPRESENTED', 'N/A', 'NONE', 'NULL', '-') THEN NULL
            ELSE ticket
        END AS ticket,
        full_name
    FROM normalized
    WHERE document IS NOT NULL
      AND document NOT IN ('', 'NOTPRESENTED', 'N/A', 'NONE', 'NULL', '-')
)
SELECT document, COUNT(DISTINCT ticket) AS flight_count,
       STRING_AGG(DISTINCT full_name, ' / ' ORDER BY full_name) AS full_name
FROM passenger_tickets
GROUP BY document
ORDER BY flight_count DESC, document;
