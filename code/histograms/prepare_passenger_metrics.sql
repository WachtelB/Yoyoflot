CREATE OR REPLACE TEMP MACRO norm_id(value) AS (
    CASE WHEN UPPER(REGEXP_REPLACE(TRIM(value), '\s+', '', 'g'))
                   IN ('', 'NOTPRESENTED', 'N/A', 'NONE', 'NULL', '-') THEN NULL
         ELSE UPPER(REGEXP_REPLACE(TRIM(value), '\s+', '', 'g')) END
);
CREATE OR REPLACE TEMP MACRO airport(value) AS (
    CASE WHEN REGEXP_FULL_MATCH(UPPER(TRIM(value)), '[A-Z]{3}')
         THEN UPPER(TRIM(value)) END
);

CREATE OR REPLACE TEMP TABLE person_records AS
SELECT norm_id(PassengerDocument) AS document, norm_id(TicketNumber) AS ticket,
       NULLIF(CONCAT_WS(' ', NULLIF(TRIM(PassengerFirstName), ''),
                            NULLIF(TRIM(PassengerSecondName), ''),
                            NULLIF(TRIM(PassengerLastName), '')), '') AS full_name,
       norm_id(FlightNumber) AS flight_number,
       TRY_CAST(FlightDate AS DATE) AS flight_date,
       TRY_CAST(FlightTime AS TIME) AS flight_time,
       NULL::VARCHAR AS origin, NULL::VARCHAR AS destination
FROM source.boarding_data
UNION ALL
SELECT norm_id(TravelDoc), norm_id("e-Ticket"), NULLIF(TRIM(PaxName), ''),
       norm_id(Flight), TRY_CAST(DepartDate AS DATE), TRY_CAST(DepartTime AS TIME),
       airport("From"), airport(Dest)
FROM source.sirena;

CREATE OR REPLACE TEMP TABLE passengers AS
SELECT document, STRING_AGG(DISTINCT full_name, ' / ' ORDER BY full_name) AS full_name
FROM person_records WHERE document IS NOT NULL GROUP BY document;

CREATE OR REPLACE TEMP TABLE ticket_owners AS
SELECT ticket, MIN(document) AS document, COUNT(DISTINCT document) AS owner_count
FROM person_records WHERE document IS NOT NULL AND ticket IS NOT NULL GROUP BY ticket;

CREATE OR REPLACE TEMP TABLE passenger_raw_flights AS
SELECT document, flight_number, flight_date, flight_time, origin, destination
FROM person_records WHERE document IS NOT NULL
UNION ALL
SELECT owners.document, norm_id(bp.flight_number), TRY_CAST(bp.raw_date AS DATE),
       TRY_CAST(bp.flight_time AS TIME), airport(bp.from_iata), airport(bp.to_iata)
FROM source.boarding_passes bp
JOIN ticket_owners owners ON norm_id(bp.e_ticket) = owners.ticket
WHERE owners.owner_count = 1;

CREATE OR REPLACE TEMP TABLE valid_passenger_flights AS
SELECT DISTINCT * FROM passenger_raw_flights
WHERE flight_number IS NOT NULL AND flight_date IS NOT NULL;

CREATE OR REPLACE TEMP TABLE passenger_day_routes AS
SELECT document, flight_number, flight_date,
       COUNT(DISTINCT (origin, destination)) FILTER (
           WHERE origin IS NOT NULL AND destination IS NOT NULL) AS route_count,
       MIN(origin) FILTER (WHERE destination IS NOT NULL) AS origin,
       MIN(destination) FILTER (WHERE origin IS NOT NULL) AS destination
FROM valid_passenger_flights GROUP BY document, flight_number, flight_date;

CREATE OR REPLACE TEMP TABLE passenger_events AS
WITH events AS (
    SELECT DISTINCT document, flight_number, flight_date, flight_time
    FROM valid_passenger_flights WHERE flight_time IS NOT NULL
    UNION ALL
    SELECT DISTINCT f.document, f.flight_number, f.flight_date, f.flight_time
    FROM valid_passenger_flights f
    WHERE f.flight_time IS NULL AND NOT EXISTS (
        SELECT 1 FROM valid_passenger_flights timed
        WHERE timed.document = f.document AND timed.flight_number = f.flight_number
          AND timed.flight_date = f.flight_date AND timed.flight_time IS NOT NULL
    )
)
SELECT e.document, e.flight_number, e.flight_date, e.flight_time,
       CASE WHEN r.route_count = 1 THEN r.origin END AS origin,
       CASE WHEN r.route_count = 1 THEN r.destination END AS destination
FROM events e JOIN passenger_day_routes r USING (document, flight_number, flight_date);
