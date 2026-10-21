import duckdb
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
REPORT_FILE = BASE_DIR / "spies_verification_report.txt"


def parquet_path(filename):
    return str((BASE_DIR / filename).resolve()).replace("'", "''").replace("\\", "/")

pd.set_option("display.max_columns", None)
pd.set_option("display.max_rows", 200)
pd.set_option("display.width", 1500)
pd.set_option("display.max_colwidth", 100)

con = duckdb.connect(str(BASE_DIR / "yoyoflot.duckdb"))
con.execute("""
    CREATE OR REPLACE TEMP MACRO as_date(value) AS (
        COALESCE(
            TRY_CAST(value AS DATE),
            CAST(TRY_STRPTIME(CAST(value AS VARCHAR), '%d.%m.%Y') AS DATE)
        )
    )
""")
con.execute(f"""
    CREATE OR REPLACE VIEW sirena AS SELECT * FROM '{parquet_path("sirena.parquet")}';
    CREATE OR REPLACE VIEW boarding_data AS SELECT * FROM '{parquet_path("parsed_data/boarding_data.parquet")}';
    CREATE OR REPLACE VIEW boarding_passes AS SELECT * FROM '{parquet_path("boarding_passes.parquet")}';
    CREATE OR REPLACE VIEW pointz_activities AS SELECT * FROM '{parquet_path("pointz_activities.parquet")}';
""")

sirena_cols = [c[0] for c in con.execute("DESCRIBE sirena").fetchall()]
fare_select = "TRIM(Fare)" if "Fare" in sirena_cols else "regexp_extract(RawRest, '([A-Z0-9]{6})', 1)"
fare_filter = f"{fare_select} IS NOT NULL AND {fare_select} != ''"

q_case1_dossier = """
SELECT 
    'Sirena' AS source,
    PaxName AS passenger_name,
    norm_birth_date AS birth_date,
    norm_flight_date AS flight_date,
    Flight AS flight_num,
    "From" || '->' || Dest AS route,
    Code AS pnr,
    norm_doc AS passport,
    norm_ff_card AS ff_card
FROM sirena 
WHERE REPLACE(norm_doc, ' ', '') = '8248013778'
UNION ALL
SELECT 
    'BoardingData' AS source,
    PassengerLastName || ' ' || PassengerFirstName || ' ' || COALESCE(PassengerSecondName, '') AS passenger_name,
    norm_birth_date AS birth_date,
    norm_flight_date AS flight_date,
    FlightNumber AS flight_num,
    Destination AS route,
    BookingCode AS pnr,
    norm_doc AS passport,
    Baggage AS ff_card
FROM boarding_data 
WHERE REPLACE(norm_doc, ' ', '') = '8248013778'
ORDER BY flight_date;
"""

q_case1_passes = """
SELECT 
    source_file,
    norm_flight_date,
    flight_number,
    from_iata || '->' || to_iata AS route,
    raw_name,
    seat,
    pnr,
    e_ticket
FROM boarding_passes 
WHERE pnr IN (SELECT Code FROM sirena WHERE REPLACE(norm_doc, ' ', '') = '8248013778')
ORDER BY as_date(norm_flight_date);
"""

q_case2_maslennikov = """
SELECT 'Sirena' AS src, PaxName AS full_name, norm_birth_date AS dob, norm_doc AS passport, 
       Flight AS flight, norm_flight_date AS f_date, "From" || '->' || Dest AS route, norm_ff_card AS ff_card
FROM sirena
WHERE (norm_last_name = 'MASLENNIKOV' AND norm_first_name = 'ROMAN')
   OR (norm_last_name = 'GOLOVINA' AND norm_first_name = 'OLESIA')
   OR REPLACE(norm_ff_card, ' ', '') = 'FB139888197'
UNION ALL
SELECT 'Boarding' AS src, PassengerLastName || ' ' || PassengerFirstName AS full_name, 
       norm_birth_date AS dob, norm_doc AS passport,
       FlightNumber AS flight, norm_flight_date AS f_date, Destination AS route, NULL AS ff_card
FROM boarding_data
WHERE (norm_last_name = 'MASLENNIKOV' AND norm_first_name = 'ROMAN')
   OR (norm_last_name = 'GOLOVINA' AND norm_first_name = 'OLESIA')
ORDER BY full_name, f_date;
"""

q_case3_fare_siphoning = f"""
WITH sirena_no_ff AS (
    SELECT 
        norm_flight_date AS f_date,
        TRIM(Flight) AS flight_no,
        {fare_select} AS fare_code,
        PaxName AS sirena_pax_ru,
        norm_last_name || ' ' || norm_first_name AS sirena_norm_name,
        norm_doc
    FROM sirena
    WHERE (norm_ff_card IS NULL OR norm_ff_card = '')
      AND {fare_filter}
),
pointz_acts AS (
    SELECT 
        flight_date AS f_date,
        TRIM(flight_number) AS flight_no,
        TRIM(fare) AS fare_code,
        bonus_program || ' ' || card_number AS ff_card,
        raw_last_name || ' ' || raw_first_name AS pointz_owner_raw,
        norm_last_name || ' ' || norm_first_name AS pointz_norm_name
    FROM pointz_activities
    WHERE fare IS NOT NULL AND TRIM(fare) != ''
),
all_pax_on_flight AS (
    SELECT DISTINCT 
        norm_flight_date AS f_date,
        TRIM(Flight) AS flight_no,
        norm_last_name || ' ' || norm_first_name AS pax_norm_name
    FROM sirena
    UNION
    SELECT DISTINCT 
        norm_flight_date AS f_date,
        TRIM(FlightNumber) AS flight_no,
        norm_last_name || ' ' || norm_first_name AS pax_norm_name
    FROM boarding_data
)
SELECT 
    s.f_date,
    s.flight_no,
    s.fare_code,
    s.sirena_pax_ru AS passenger_in_sirena,
    s.norm_doc AS passenger_passport,
    p.ff_card AS credited_card,
    p.pointz_owner_raw AS card_owner_in_pointz,
    CASE 
        WHEN a.pax_norm_name IS NOT NULL THEN 'COLLISION_SAME_FLIGHT'
        ELSE 'CONFIRMED_SPY_MILEAGE_SIPHONING'
    END AS verdict
FROM sirena_no_ff s
JOIN pointz_acts p 
  ON s.f_date = p.f_date AND s.flight_no = p.flight_no AND s.fare_code = p.fare_code
LEFT JOIN all_pax_on_flight a
  ON p.f_date = a.f_date AND p.flight_no = a.flight_no AND p.pointz_norm_name = a.pax_norm_name
WHERE s.sirena_norm_name != p.pointz_norm_name
ORDER BY verdict DESC, as_date(s.f_date);
"""

q_case4_foreign_passport_swaps = """
WITH pnr_9d_suspects AS (
    SELECT DISTINCT 
        s.PaxName AS sirena_name,
        s.norm_doc AS doc_sirena,
        b.norm_doc AS doc_boarding,
        s.Code AS pnr
    FROM sirena s
    JOIN boarding_data b ON s.Code = b.norm_pnr AND TRIM(s.Flight) = TRIM(b.FlightNumber)
    WHERE s.norm_doc != b.norm_doc
      AND LENGTH(REPLACE(s.norm_doc, ' ', '')) = 9
      AND LENGTH(REPLACE(b.norm_doc, ' ', '')) = 9
)
SELECT 
    p.sirena_name,
    p.pnr,
    p.doc_sirena,
    p.doc_boarding,
    COUNT(DISTINCT s_all.Flight || '_' || s_all.norm_flight_date) AS total_flights_sirena,
    COUNT(DISTINCT b_all.FlightNumber || '_' || b_all.norm_flight_date) AS total_flights_boarding,
    MAX(s_all.norm_ff_card) AS loyalty_card
FROM pnr_9d_suspects p
LEFT JOIN sirena s_all ON (s_all.norm_doc = p.doc_sirena OR s_all.norm_doc = p.doc_boarding)
LEFT JOIN boarding_data b_all ON (b_all.norm_doc = p.doc_sirena OR b_all.norm_doc = p.doc_boarding)
GROUP BY p.sirena_name, p.pnr, p.doc_sirena, p.doc_boarding
ORDER BY total_flights_boarding DESC, total_flights_sirena DESC
LIMIT 25;
"""

with open(REPORT_FILE, "w", encoding="utf-8") as f:
    f.write("CASE 1: DUPLICATE PASSPORT 8248 013778 (GLEBOV GORDEI vs BUROV RAMIL)\n")
    f.write(con.execute(q_case1_dossier).df().to_string(index=False) + "\n\n")
    f.write("CASE 1 BOARDING PASSES:\n")
    f.write(con.execute(q_case1_passes).df().to_string(index=False) + "\n\n")

    f.write("CASE 2: COMPROMISED LOYALTY CARD FB 139888197 (MASLENNIKOV ROMAN vs GOLOVINA OLESIA)\n")
    f.write(con.execute(q_case2_maslennikov).df().to_string(index=False) + "\n\n")

    f.write("CASE 3: FARE CODE MILEAGE SIPHONING VERIFICATION\n")
    f.write(con.execute(q_case3_fare_siphoning).df().to_string(index=False) + "\n\n")

    f.write("CASE 4: SYSTEMATIC 9-DIGIT FOREIGN PASSPORT ROTATION AT BOARDING\n")
    f.write(con.execute(q_case4_foreign_passport_swaps).df().to_string(index=False) + "\n")

con.close()
