import duckdb
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
REPORT_FILE = BASE_DIR / "entity_resolution_report.txt"

def parquet_path(filename):
    return str((BASE_DIR / filename).resolve()).replace("'", "''").replace("\\", "/")


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
    CREATE OR REPLACE VIEW boarding AS SELECT * FROM '{parquet_path("parsed_data/boarding_data.parquet")}';
    CREATE OR REPLACE VIEW passes AS SELECT * FROM '{parquet_path("boarding_passes.parquet")}';
    CREATE OR REPLACE VIEW pointz AS SELECT * FROM '{parquet_path("pointz_activities.parquet")}';
    CREATE OR REPLACE VIEW pointz_users AS SELECT * FROM '{parquet_path("pointz_users_cards.parquet")}';
    CREATE OR REPLACE VIEW skyteam AS SELECT * FROM '{parquet_path("skyteam_exchange.parquet")}';
    CREATE OR REPLACE VIEW forum_users AS SELECT * FROM '{parquet_path("forum_users.parquet")}';
    CREATE OR REPLACE VIEW forum_flights AS SELECT * FROM '{parquet_path("forum_flights.parquet")}';
    CREATE OR REPLACE VIEW forum_loyalty AS SELECT * FROM '{parquet_path("forum_loyalty.parquet")}';
""")

sirena_cols = [c[0] for c in con.execute("DESCRIBE sirena").fetchall()]
s_ticket_col = "eTicket" if "eTicket" in sirena_cols else '"e-Ticket"'
fare_expr = "TRIM(Fare)" if "Fare" in sirena_cols else "regexp_extract(RawRest, '([A-Z0-9]{6})', 1)"

pd.set_option("display.max_columns", None)
pd.set_option("display.max_rows", 200)
pd.set_option("display.width", 1500)
pd.set_option("display.max_colwidth", None)

with open(REPORT_FILE, "w", encoding="utf-8") as out:

    def write_section(num, title, sql_query):
        out.write(f"[{num}/8] {title}\n")
        df = con.execute(sql_query).df()
        if df.empty:
            out.write("No anomalies found.\n\n")
        else:
            out.write(f"Records found: {len(df)}\n")
            out.write(df.to_string(index=False) + "\n\n")

    write_section(
        1,
        "PASSPORT COLLISIONS (DIFFERENT NAMES OR BIRTH DATES FOR ONE PASSPORT)",
        """
        WITH all_docs AS (
            SELECT norm_doc, norm_last_name, norm_first_name, patronymic_initial, norm_birth_date, 'Sirena' AS src
            FROM sirena WHERE norm_doc IS NOT NULL AND norm_doc != ''
            UNION ALL
            SELECT norm_doc, norm_last_name, norm_first_name, patronymic_initial, norm_birth_date, 'Boarding' AS src
            FROM boarding WHERE norm_doc IS NOT NULL AND norm_doc != ''
        )
        SELECT 
            norm_doc AS passport,
            COUNT(DISTINCT norm_last_name || '_' || norm_first_name) AS diff_names,
            COUNT(DISTINCT norm_birth_date) AS diff_dobs,
            STRING_AGG(DISTINCT norm_last_name || ' ' || norm_first_name || ' ' || COALESCE(patronymic_initial, ''), ' | ') AS passenger_names,
            STRING_AGG(DISTINCT norm_birth_date, ', ') AS birth_dates,
            STRING_AGG(DISTINCT src, ', ') AS sources
        FROM all_docs
        GROUP BY norm_doc
        HAVING COUNT(DISTINCT norm_last_name) > 1 
            OR COUNT(DISTINCT norm_first_name) > 1 
            OR COUNT(DISTINCT norm_birth_date) > 1
        ORDER BY diff_names DESC, diff_dobs DESC;
        """
    )

    write_section(
        2,
        "MULTIPLE PASSPORTS OF THE SAME TYPE PER PERSON",
        """
        WITH person_docs AS (
            SELECT norm_last_name, norm_first_name, patronymic_initial, norm_birth_date, norm_doc,
                   LENGTH(REPLACE(norm_doc, ' ', '')) AS d_len
            FROM sirena WHERE norm_doc IS NOT NULL AND norm_doc != ''
            UNION ALL
            SELECT norm_last_name, norm_first_name, patronymic_initial, norm_birth_date, norm_doc,
                   LENGTH(REPLACE(norm_doc, ' ', '')) AS d_len
            FROM boarding WHERE norm_doc IS NOT NULL AND norm_doc != ''
        )
        SELECT 
            norm_last_name || ' ' || norm_first_name || ' ' || COALESCE(patronymic_initial, '') AS person,
            MAX(norm_birth_date) AS dob,
            COUNT(DISTINCT norm_doc) AS total_docs,
            COUNT(DISTINCT CASE WHEN d_len = 10 THEN norm_doc END) AS internal_10d_docs,
            COUNT(DISTINCT CASE WHEN d_len = 9 THEN norm_doc END) AS foreign_9d_docs,
            STRING_AGG(DISTINCT norm_doc, ', ') AS passport_numbers
        FROM person_docs
        WHERE norm_last_name != '' AND norm_first_name != ''
        GROUP BY norm_last_name, norm_first_name, patronymic_initial
        HAVING COUNT(DISTINCT norm_doc) >= 3
            OR COUNT(DISTINCT CASE WHEN d_len = 10 THEN norm_doc END) >= 2
            OR COUNT(DISTINCT CASE WHEN d_len = 9 THEN norm_doc END) >= 2
        ORDER BY total_docs DESC, internal_10d_docs DESC
        LIMIT 50;
        """
    )

    write_section(
        3,
        "PING-PONG PASSPORT ALTERNATION OVER TIME",
        """
        WITH person_docs AS (
            SELECT norm_last_name, norm_first_name, patronymic_initial, norm_doc,
                   LENGTH(REPLACE(norm_doc, ' ', '')) AS doc_len,
                    as_date(norm_flight_date) AS dt
            FROM sirena WHERE norm_doc IS NOT NULL AND norm_doc != ''
            UNION ALL
            SELECT norm_last_name, norm_first_name, patronymic_initial, norm_doc,
                   LENGTH(REPLACE(norm_doc, ' ', '')) AS doc_len,
                   as_date(norm_flight_date) AS dt
            FROM boarding WHERE norm_doc IS NOT NULL AND norm_doc != ''
        ),
        bounds AS (
            SELECT 
                norm_last_name, norm_first_name, patronymic_initial, doc_len, norm_doc,
                MIN(dt) AS first_dt,
                MAX(dt) AS last_dt
            FROM person_docs
            WHERE dt IS NOT NULL
            GROUP BY norm_last_name, norm_first_name, patronymic_initial, doc_len, norm_doc
        )
        SELECT 
            b1.norm_last_name || ' ' || b1.norm_first_name || ' ' || COALESCE(b1.patronymic_initial, '') AS person,
            b1.doc_len AS passport_digits,
            b1.norm_doc AS passport_A,
            STRFTIME(b1.first_dt, '%d.%m.%Y') || ' .. ' || STRFTIME(b1.last_dt, '%d.%m.%Y') AS period_A,
            b2.norm_doc AS passport_B,
            STRFTIME(b2.first_dt, '%d.%m.%Y') || ' .. ' || STRFTIME(b2.last_dt, '%d.%m.%Y') AS period_B
        FROM bounds b1
        JOIN bounds b2
          ON b1.norm_last_name = b2.norm_last_name
         AND b1.norm_first_name = b2.norm_first_name
         AND COALESCE(b1.patronymic_initial, '') = COALESCE(b2.patronymic_initial, '')
         AND b1.doc_len = b2.doc_len
         AND b1.norm_doc < b2.norm_doc
        WHERE b1.first_dt < b2.last_dt AND b2.first_dt < b1.last_dt
        LIMIT 50;
        """
    )

    write_section(
        4,
        "LOYALTY CARD OWNER MISMATCH (SIRENA vs POINTZ XML vs FORUM JSON)",
        """
        WITH all_card_owners AS (
            SELECT REPLACE(norm_ff_card, ' ', '') AS clean_card, norm_last_name, norm_first_name, 'Sirena' AS src
            FROM sirena WHERE norm_ff_card IS NOT NULL AND norm_ff_card != ''
            UNION ALL
            SELECT REPLACE(card_number, ' ', '') AS clean_card, norm_last_name, norm_first_name, 'PointzXML' AS src
            FROM pointz_users WHERE card_number IS NOT NULL AND card_number != ''
            UNION ALL
            SELECT REPLACE(fl.norm_ff_card, ' ', '') AS clean_card, fu.norm_last_name, fu.norm_first_name, 'ForumJSON' AS src
            FROM forum_loyalty fl
            JOIN forum_users fu ON fl.profile_id = fu.profile_id
            WHERE fl.norm_ff_card IS NOT NULL AND fu.norm_last_name != ''
        )
        SELECT 
            clean_card AS loyalty_card,
            COUNT(DISTINCT norm_last_name) AS diff_last_names,
            STRING_AGG(DISTINCT norm_last_name || ' ' || norm_first_name || ' [' || src || ']', ' | ') AS registered_owners
        FROM all_card_owners
        WHERE clean_card != ''
        GROUP BY clean_card
        HAVING COUNT(DISTINCT norm_last_name) > 1
        ORDER BY diff_last_names DESC;
        """
    )

    write_section(
        5,
        "E-TICKET NAME SWAP (SIRENA vs BOARDING PASSES)",
        f"""
        SELECT 
            s.{s_ticket_col} AS e_ticket,
            s.Flight AS flight,
            s.norm_flight_date AS flight_date,
            s.PaxName AS sirena_booking_name,
            bp.raw_name AS boarding_pass_name,
            s.Code AS sirena_pnr,
            bp.pnr AS bp_pnr,
            s.norm_doc AS passport
        FROM sirena s
        JOIN passes bp 
          ON s.{s_ticket_col} = bp.e_ticket
        WHERE s.norm_last_name != bp.norm_name_part1 
          AND s.norm_last_name != bp.norm_name_part2
        LIMIT 50;
        """
    )

    write_section(
        6,
        "FARE CODE MILEAGE SIPHONING (FLIGHT + DATE + FARE)",
        f"""
        WITH s_fares AS (
            SELECT 
                norm_flight_date AS f_date,
                TRIM(Flight) AS flight_no,
                {fare_expr} AS fare_code,
                PaxName,
                norm_last_name,
                norm_doc
            FROM sirena
            WHERE norm_ff_card IS NULL OR norm_ff_card = ''
        )
        SELECT 
            sf.f_date,
            sf.flight_no,
            sf.fare_code,
            sf.PaxName AS sirena_passenger,
            sf.norm_doc AS sirena_passport,
            p.card_number AS pointz_loyalty_card,
            p.norm_last_name || ' ' || p.norm_first_name AS pointz_card_owner
        FROM s_fares sf
        JOIN pointz p
          ON sf.f_date = p.flight_date
         AND sf.flight_no = TRIM(p.flight_number)
         AND sf.fare_code = TRIM(p.fare)
        WHERE sf.fare_code IS NOT NULL 
          AND sf.fare_code != ''
          AND sf.norm_last_name != p.norm_last_name
        LIMIT 50;
        """
    )

    write_section(
        7,
        "CROSS-SYSTEM SAME-DAY PARALLEL FLIGHTS BY LOYALTY CARD",
        """
        WITH all_ff AS (
            SELECT REPLACE(norm_ff_card, ' ', '') AS card, norm_flight_date AS f_date, Flight AS flight_no, "From" AS dep, Dest AS arr, 'Sirena' AS src
            FROM sirena WHERE norm_ff_card IS NOT NULL AND norm_ff_card != ''
            UNION ALL
            SELECT REPLACE(card_number, ' ', '') AS card, flight_date AS f_date, flight_number AS flight_no, origin AS dep, destination AS arr, 'Pointz' AS src
            FROM pointz WHERE card_number IS NOT NULL AND card_number != ''
            UNION ALL
            SELECT REPLACE(norm_ff_card, ' ', '') AS card, flight_date AS f_date, flight_number AS flight_no, from_iata AS dep, to_iata AS arr, 'SkyTeam' AS src
            FROM skyteam WHERE norm_ff_card IS NOT NULL AND norm_ff_card != ''
            UNION ALL
            SELECT REPLACE(fl.norm_ff_card, ' ', '') AS card, ff.flight_date AS f_date, ff.flight_number AS flight_no, ff.from_iata AS dep, ff.to_iata AS arr, 'Forum' AS src
            FROM forum_flights ff
            JOIN forum_loyalty fl ON ff.profile_id = fl.profile_id
            WHERE fl.norm_ff_card IS NOT NULL
        ),
        dedup AS (
            SELECT DISTINCT card, f_date, flight_no, dep, arr, src FROM all_ff WHERE card != ''
        )
        SELECT 
            f1.card AS loyalty_card,
            f1.f_date AS flight_date,
            f1.flight_no || ' (' || f1.dep || '->' || f1.arr || ') [' || f1.src || ']' AS flight_1,
            f2.flight_no || ' (' || f2.dep || '->' || f2.arr || ') [' || f2.src || ']' AS flight_2
        FROM dedup f1
        JOIN dedup f2
          ON f1.card = f2.card
         AND f1.f_date = f2.f_date
         AND f1.flight_no < f2.flight_no
         AND f1.dep != f2.dep
         AND f1.arr != f2.arr
         AND f1.arr != f2.dep
         AND f2.arr != f1.dep
        LIMIT 50;
        """
    )

    write_section(
        8,
        "PNR PASSENGER DATA MISMATCH (SIRENA vs BOARDING DATA)",
        """
        SELECT 
            s.Code AS pnr,
            s.Flight AS flight,
            s.norm_flight_date AS flight_date,
            s.PaxName AS sirena_name,
            b.norm_last_name || ' ' || b.norm_first_name AS boarding_name,
            s.norm_doc AS sirena_passport,
            b.norm_doc AS boarding_passport,
            s.norm_birth_date AS sirena_dob,
            b.norm_birth_date AS boarding_dob
        FROM sirena s
        JOIN boarding b
          ON s.Code = b.norm_pnr
         AND TRIM(s.Flight) = TRIM(b.FlightNumber)
         AND s.norm_flight_date = b.norm_flight_date
         AND s.norm_last_name = b.norm_last_name
         AND s.norm_first_name = b.norm_first_name
        WHERE (s.norm_doc IS NOT NULL AND b.norm_doc IS NOT NULL AND s.norm_doc != b.norm_doc)
           OR (s.norm_birth_date IS NOT NULL AND b.norm_birth_date IS NOT NULL AND s.norm_birth_date != b.norm_birth_date)
        LIMIT 50;
        """
    )

con.close()
