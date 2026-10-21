CREATE OR REPLACE TEMP TABLE graph_nodes AS
SELECT ROW_NUMBER() OVER (ORDER BY document) - 1 AS node_id, document, full_name
FROM passengers;

CREATE OR REPLACE TEMP TABLE graph_conflicts AS
SELECT document, flight_number, flight_date
FROM valid_passenger_flights
GROUP BY document, flight_number, flight_date
HAVING COUNT(DISTINCT flight_time) > 1;

CREATE OR REPLACE TEMP TABLE graph_events AS
SELECT DISTINCT e.* FROM passenger_events e
WHERE flight_time IS NOT NULL AND origin IS NOT NULL AND destination IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM graph_conflicts c
    WHERE c.document = e.document AND c.flight_number = e.flight_number
      AND c.flight_date = e.flight_date
  );

CREATE OR REPLACE TEMP TABLE graph_flights AS
SELECT ROW_NUMBER() OVER (ORDER BY flight_date, flight_time, flight_number, origin, destination) - 1 AS flight_id,
       flight_number, flight_date, flight_time, origin, destination,
       COUNT(DISTINCT document) AS passengers
FROM graph_events
GROUP BY flight_number, flight_date, flight_time, origin, destination;

CREATE OR REPLACE TEMP TABLE graph_memberships AS
SELECT DISTINCT n.node_id, f.flight_id
FROM graph_events e JOIN graph_nodes n USING (document)
JOIN graph_flights f USING (flight_number, flight_date, flight_time, origin, destination);

CREATE OR REPLACE TEMP TABLE graph_edges AS
SELECT a.node_id AS source, b.node_id AS target,
       LIST(a.flight_id ORDER BY a.flight_id) AS flights
FROM graph_memberships a JOIN graph_memberships b ON a.flight_id = b.flight_id AND a.node_id < b.node_id
GROUP BY a.node_id, b.node_id;
