import os
import duckdb
import pandas as pd

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.abspath(os.path.join(SRC_DIR, "..", "databaze"))
sirena_parquet = os.path.join(DB_DIR, "sirena.parquet")
airports_csv = os.path.join(SRC_DIR, "airports_reference.csv")
REPORT_FILE = os.path.join(SRC_DIR, "time_paradoxes_report.txt")

print("=" * 100)
print("             ШАГ 3: ПОИСК ВРЕМЕННЫХ ПАРАДОКСОВ И ШПИОНОВ (DUCKDB)")
print("=" * 100)

con = duckdb.connect()
con.execute("SET memory_limit = '8GB';")
con.execute("SET threads TO 4;")


sirena_cols = [
    row[0]
    for row in con.execute(f"DESCRIBE SELECT * FROM '{sirena_parquet}'").fetchall()
]

doc_col = (
    "norm_doc"
    if "norm_doc" in sirena_cols
    else "REGEXP_REPLACE(COALESCE(TravelDoc, ''), '[^0-9A-Za-z]', '', 'g')"
)
card_col = (
    "norm_ff_card"
    if "norm_ff_card" in sirena_cols
    else "TRIM(REGEXP_EXTRACT(PaxAdditionalInfo, 'FF#([A-Z0-9 ]+)', 1))"
)

print(f"[*] Идентификатор паспорта: {doc_col}")
print(f"[*] Идентификатор карты FF: {card_col}")

con.execute(f"""
    CREATE OR REPLACE TABLE airports AS 
    SELECT 
        iata,
        city,
        country,
        lat,
        lon,
        COALESCE(timezone, 'UTC') AS timezone
    FROM read_csv_auto('{airports_csv}');

    -- Макрос расчета расстояния на сфере Земли (в км)
    CREATE OR REPLACE MACRO haversine_km(lat1, lon1, lat2, lon2) AS (
        2 * 6371 * asin(sqrt(
            pow(sin(radians(lat2 - lat1) / 2), 2) +
            cos(radians(lat1)) * cos(radians(lat2)) *
            pow(sin(radians(lon2 - lon1) / 2), 2)
        ))
    );
""")

print("[*] Перевод локальных дат и времен вылета/прилета в UTC...")
con.execute(f"""
    CREATE OR REPLACE TABLE flights_utc AS
    WITH raw_flights AS (
        SELECT 
            {doc_col} AS passport,
            {card_col} AS ff_card,
            PaxName AS person_name,
            PaxBirthDate AS birth_date,
            Flight AS flight_no,
            UPPER(TRIM("From")) AS origin,
            UPPER(TRIM(Dest)) AS destination,
            CodeSh AS is_codeshare,
            Code AS pnr,
            TRY_CAST(DepartDate || ' ' || DepartTime AS TIMESTAMP) AS dep_local,
            TRY_CAST(ArrivalDate || ' ' || ArrivalTime AS TIMESTAMP) AS arr_local
        FROM '{sirena_parquet}'
        WHERE DepartDate IS NOT NULL AND DepartTime IS NOT NULL
          AND ArrivalDate IS NOT NULL AND ArrivalTime IS NOT NULL
    )
    SELECT 
        f.passport,
        f.ff_card,
        f.person_name,
        f.birth_date,
        f.flight_no,
        f.origin,
        f.destination,
        f.is_codeshare,
        f.pnr,
        a_dep.city AS origin_city,
        a_arr.city AS dest_city,
        a_dep.lat AS dep_lat, a_dep.lon AS dep_lon,
        a_arr.lat AS arr_lat, a_arr.lon AS arr_lon,
        -- Конвертация в UTC с учетом таймзоны аэропорта
        timezone(a_dep.timezone, f.dep_local) AS dep_utc,
        timezone(a_arr.timezone, f.arr_local) AS arr_utc
    FROM raw_flights f
    LEFT JOIN airports a_dep ON f.origin = a_dep.iata
    LEFT JOIN airports a_arr ON f.destination = a_arr.iata
    WHERE f.dep_local IS NOT NULL AND f.arr_local IS NOT NULL
      AND f.dep_local <= f.arr_local; -- Защита от поврежденных записей
""")

total_flights = con.execute("SELECT COUNT(*) FROM flights_utc").fetchone()[0]
print(f"[+] Обработано и приведено к UTC рейсов: {total_flights}")

report_lines = []


def log(text=""):
    print(text)
    report_lines.append(text)


log("\n" + "=" * 100)
log("             [ТИП 1] ОДНОВРЕМЕННЫЕ ПЕРЕЛЕТЫ (ОДИН ЧЕЛОВЕК НА 2 БОРТАХ)")
log("=" * 100)

query_overlap_doc = """
WITH multi_docs AS (
    SELECT passport FROM flights_utc 
    WHERE passport IS NOT NULL AND passport != ''
    GROUP BY passport HAVING COUNT(*) > 1
)
SELECT 
    f1.passport,
    f1.person_name AS name_flight_1,
    f2.person_name AS name_flight_2,
    f1.flight_no AS flight_1,
    f1.origin || '->' || f1.destination AS route_1,
    f1.dep_utc AS dep_utc_1,
    f1.arr_utc AS arr_utc_1,
    f2.flight_no AS flight_2,
    f2.origin || '->' || f2.destination AS route_2,
    f2.dep_utc AS dep_utc_2,
    f2.arr_utc AS arr_utc_2
FROM flights_utc f1
JOIN multi_docs m ON f1.passport = m.passport
JOIN flights_utc f2 ON f1.passport = f2.passport
WHERE f1.flight_no < f2.flight_no
  -- Фильтр код-шеринга: одинаковые города и вылет с разницей менее 60 мин
  AND NOT (f1.origin = f2.origin AND f1.destination = f2.destination 
           AND abs(epoch(f1.dep_utc) - epoch(f2.dep_utc)) < 3600)
  -- Пересечение временных интервалов:
  AND f1.dep_utc < f2.arr_utc 
  AND f2.dep_utc < f1.arr_utc
ORDER BY f1.dep_utc;
"""

df_overlap_doc = con.execute(query_overlap_doc).df()
log(f"\n[1.1] Найдено пересечений по ПАСПОРТУ: {len(df_overlap_doc)}")
if not df_overlap_doc.empty:
    log(df_overlap_doc.to_string(index=False))
else:
    log("Прямых наложений по номерам паспортов не найдено.")

query_overlap_card = """
WITH multi_cards AS (
    SELECT ff_card FROM flights_utc 
    WHERE ff_card IS NOT NULL AND ff_card != ''
    GROUP BY ff_card HAVING COUNT(*) > 1
)
SELECT 
    f1.ff_card,
    f1.passport AS passport_1,
    f1.person_name AS name_1,
    f2.passport AS passport_2,
    f2.person_name AS name_2,
    f1.flight_no AS flight_1,
    f1.origin || '->' || f1.destination AS route_1,
    f1.dep_utc AS dep_utc_1,
    f1.arr_utc AS arr_utc_1,
    f2.flight_no AS flight_2,
    f2.origin || '->' || f2.destination AS route_2,
    f2.dep_utc AS dep_utc_2,
    f2.arr_utc AS arr_utc_2
FROM flights_utc f1
JOIN multi_cards m ON f1.ff_card = m.ff_card
JOIN flights_utc f2 ON f1.ff_card = f2.ff_card
WHERE f1.flight_no < f2.flight_no
  AND NOT (f1.origin = f2.origin AND f1.destination = f2.destination 
           AND abs(epoch(f1.dep_utc) - epoch(f2.dep_utc)) < 3600)
  AND f1.dep_utc < f2.arr_utc 
  AND f2.dep_utc < f1.arr_utc
ORDER BY f1.dep_utc;
"""

df_overlap_card = con.execute(query_overlap_card).df()
log(f"\n[1.2] Найдено пересечений по КАРТЕ ЛОЯЛЬНОСТИ: {len(df_overlap_card)}")
if not df_overlap_card.empty:
    log(df_overlap_card.to_string(index=False))
else:
    log("Прямых наложений по картам лояльности не найдено.")


log("\n" + "=" * 100)
log("             [ТИП 2] ТЕЛЕПОРТАЦИЯ (НЕРЕАЛЬНАЯ СКОРОСТЬ / НЕДОСТАТОЧНЫЙ ТРАНСФЕР)")
log("=" * 100)

query_teleport_doc = """
WITH ordered_flights AS (
    SELECT 
        passport,
        person_name,
        flight_no,
        origin,
        destination,
        origin_city,
        dest_city,
        dep_utc,
        arr_utc,
        arr_lat,
        arr_lon,
        LEAD(flight_no) OVER w AS next_flight,
        LEAD(origin) OVER w AS next_origin,
        LEAD(origin_city) OVER w AS next_origin_city,
        LEAD(dep_utc) OVER w AS next_dep_utc,
        LEAD(dep_lat) OVER w AS next_dep_lat,
        LEAD(dep_lon) OVER w AS next_dep_lon,
        epoch(LEAD(dep_utc) OVER w - arr_utc) / 3600.0 AS ground_hours
    FROM flights_utc
    WHERE passport IS NOT NULL AND passport != ''
    WINDOW w AS (PARTITION BY passport ORDER BY dep_utc)
),
metrics AS (
    SELECT 
        passport,
        person_name,
        flight_no AS flight_1,
        origin || '->' || destination AS route_1,
        arr_utc AS arr_utc_1,
        next_flight AS flight_2,
        next_origin || ' (' || COALESCE(next_origin_city, '') || ')' AS next_dep,
        next_dep_utc AS dep_utc_2,
        ROUND(ground_hours * 60.0, 1) AS transfer_minutes,
        ROUND(haversine_km(arr_lat, arr_lon, next_dep_lat, next_dep_lon), 1) AS distance_km,
        CASE 
            WHEN ground_hours > 0 
            THEN haversine_km(arr_lat, arr_lon, next_dep_lat, next_dep_lon) / ground_hours 
            ELSE 99999.0 
        END AS required_speed_kmh
    FROM ordered_flights
    WHERE next_flight IS NOT NULL
      AND destination != next_origin -- Прилетел в один аэропорт, а вылетает из другого
)
SELECT 
    passport,
    person_name,
    flight_1,
    route_1,
    arr_utc_1,
    flight_2,
    next_dep,
    dep_utc_2,
    transfer_minutes,
    distance_km,
    ROUND(required_speed_kmh, 1) AS required_speed_kmh
FROM metrics
WHERE 
  -- Либо следующий вылет раньше текущего прилета (transfer < 0)
  transfer_minutes < 0
  -- Либо расстояние между аэропортами > 50 км и требуется нереальная скорость (> 750 км/ч)
  OR (distance_km > 50 AND required_speed_kmh > 750)
  -- Либо аэропорты разные, расстояние > 30 км, а времени на трансфер < 45 минут
  OR (distance_km > 30 AND transfer_minutes < 45)
ORDER BY transfer_minutes ASC;
"""

df_teleport_doc = con.execute(query_teleport_doc).df()
log(f"\n[2.1] Найдено случаев ТЕЛЕПОРТАЦИИ по ПАСПОРТУ: {len(df_teleport_doc)}")
if not df_teleport_doc.empty:
    log(df_teleport_doc.to_string(index=False))
else:
    log("Случаев телепортации по паспорту не обнаружено.")

query_teleport_card = """
WITH ordered_flights AS (
    SELECT 
        ff_card,
        passport,
        person_name,
        flight_no,
        origin,
        destination,
        dep_utc,
        arr_utc,
        arr_lat,
        arr_lon,
        LEAD(flight_no) OVER w AS next_flight,
        LEAD(origin) OVER w AS next_origin,
        LEAD(dep_utc) OVER w AS next_dep_utc,
        LEAD(dep_lat) OVER w AS next_dep_lat,
        LEAD(dep_lon) OVER w AS next_dep_lon,
        epoch(LEAD(dep_utc) OVER w - arr_utc) / 3600.0 AS ground_hours
    FROM flights_utc
    WHERE ff_card IS NOT NULL AND ff_card != ''
    WINDOW w AS (PARTITION BY ff_card ORDER BY dep_utc)
),
metrics AS (
    SELECT 
        ff_card,
        passport,
        person_name,
        flight_no AS flight_1,
        origin || '->' || destination AS route_1,
        arr_utc AS arr_utc_1,
        next_flight AS flight_2,
        next_origin AS next_dep,
        next_dep_utc AS dep_utc_2,
        ROUND(ground_hours * 60.0, 1) AS transfer_minutes,
        ROUND(haversine_km(arr_lat, arr_lon, next_dep_lat, next_dep_lon), 1) AS distance_km,
        CASE 
            WHEN ground_hours > 0 
            THEN haversine_km(arr_lat, arr_lon, next_dep_lat, next_dep_lon) / ground_hours 
            ELSE 99999.0 
        END AS required_speed_kmh
    FROM ordered_flights
    WHERE next_flight IS NOT NULL
      AND destination != next_origin
)
SELECT 
    ff_card,
    passport,
    person_name,
    flight_1,
    route_1,
    arr_utc_1,
    flight_2,
    next_dep,
    dep_utc_2,
    transfer_minutes,
    distance_km,
    ROUND(required_speed_kmh, 1) AS required_speed_kmh
FROM metrics
WHERE 
  transfer_minutes < 0
  OR (distance_km > 50 AND required_speed_kmh > 750)
  OR (distance_km > 30 AND transfer_minutes < 45)
ORDER BY transfer_minutes ASC;
"""

df_teleport_card = con.execute(query_teleport_card).df()
log(
    f"\n[2.2] Найдено случаев ТЕЛЕПОРТАЦИИ по КАРТЕ ЛОЯЛЬНОСТИ: {len(df_teleport_card)}"
)
if not df_teleport_card.empty:
    log(df_teleport_card.head(30).to_string(index=False))
else:
    log("Случаев телепортации по карте лояльности не обнаружено.")

with open(REPORT_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(report_lines))

log("\n" + "=" * 100)
log(f"[+] Расследование успешно завершено. Отчёт сохранен в: {REPORT_FILE}")
log("=" * 100)
con.close()
