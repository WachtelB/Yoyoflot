import os
import duckdb
import pandas as pd

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.abspath(os.path.join(SRC_DIR, "..", "databaze"))
sirena_parquet = os.path.join(DB_DIR, "sirena.parquet")
airports_csv = os.path.join(SRC_DIR, "airports_reference.csv")
output_csv = os.path.join(SRC_DIR, "express_couriers.csv")
report_txt = os.path.join(SRC_DIR, "express_couriers_report.txt")

print("=" * 100)
print("       ПОИСК ШПИОНОВ: ПАТТЕРН «ЧЕЛНОКИ» И ЭКСПРЕСС-ВИЗИТЫ (ПРЕБЫВАНИЕ <= 12 ЧАСОВ)")
print("=" * 100)

con = duckdb.connect()
con.execute("SET memory_limit = '6GB';")
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
baggage_col = "Baggage" if "Baggage" in sirena_cols else "NULL"

print(f"[*] Колонка паспорта: {doc_col}")
print(f"[*] Колонка багажа:   {baggage_col}")

con.execute(f"""
    CREATE OR REPLACE TABLE airports AS 
    SELECT 
        iata,
        city,
        lat,
        lon,
        COALESCE(timezone, 'UTC') AS timezone
    FROM read_csv_auto('{airports_csv}');

    CREATE OR REPLACE MACRO haversine_km(lat1, lon1, lat2, lon2) AS (
        2 * 6371 * asin(sqrt(
            pow(sin(radians(lat2 - lat1) / 2), 2) +
            cos(radians(lat1)) * cos(radians(lat2)) *
            pow(sin(radians(lon2 - lon1) / 2), 2)
        ))
    );
""")

print("[*] Обработка хронологии рейсов каждого пассажира в UTC...")
con.execute(f"""
    CREATE OR REPLACE TABLE flights_timeline AS
    WITH raw_flights AS (
        SELECT 
            {doc_col} AS passport,
            TRIM(PaxName) AS person_name,
            Flight AS flight_no,
            UPPER(TRIM("From")) AS origin,
            UPPER(TRIM(Dest)) AS destination,
            TRIM(Code) AS pnr,
            COALESCE({baggage_col}, 'None') AS baggage,
            TRY_CAST(DepartDate || ' ' || DepartTime AS TIMESTAMP) AS dep_local,
            TRY_CAST(ArrivalDate || ' ' || ArrivalTime AS TIMESTAMP) AS arr_local
        FROM '{sirena_parquet}'
        WHERE DepartDate IS NOT NULL AND DepartTime IS NOT NULL
          AND ArrivalDate IS NOT NULL AND ArrivalTime IS NOT NULL
    )
    SELECT 
        f.passport,
        f.person_name,
        f.flight_no,
        f.origin,
        f.destination,
        a_dep.city AS origin_city,
        a_arr.city AS dest_city,
        f.pnr,
        f.baggage,
        a_dep.lat AS dep_lat, a_dep.lon AS dep_lon,
        a_arr.lat AS arr_lat, a_arr.lon AS arr_lon,
        haversine_km(a_dep.lat, a_dep.lon, a_arr.lat, a_arr.lon) AS flight_distance_km,
        timezone(a_dep.timezone, f.dep_local) AS dep_utc,
        timezone(a_arr.timezone, f.arr_local) AS arr_utc
    FROM raw_flights f
    LEFT JOIN airports a_dep ON f.origin = a_dep.iata
    LEFT JOIN airports a_arr ON f.destination = a_arr.iata
    WHERE f.dep_local IS NOT NULL AND f.arr_local IS NOT NULL
      AND f.passport != '';
""")

print("[*] Поиск перелетов с временем пребывания <= 12 часов...")

query = """
WITH sequenced AS (
    SELECT 
        passport,
        person_name,
        flight_no AS flight_1,
        origin AS origin_1,
        destination AS city_stop,
        origin_city AS origin_city_1,
        dest_city AS stop_city_name,
        dep_utc AS dep_utc_1,
        arr_utc AS arr_utc_1,
        pnr AS pnr_1,
        baggage AS baggage_1,
        flight_distance_km AS distance_leg1_km,

        -- Следующий рейс
        LEAD(flight_no) OVER w AS flight_2,
        LEAD(origin) OVER w AS next_origin,
        LEAD(destination) OVER w AS destination_2,
        LEAD(origin_city) OVER w AS next_origin_city,
        LEAD(dest_city) OVER w AS dest_city_2,
        LEAD(dep_utc) OVER w AS next_dep_utc,
        LEAD(pnr) OVER w AS pnr_2,
        LEAD(baggage) OVER w AS baggage_2,

        -- Время пребывания в транзитном городе (в часах)
        ROUND(epoch(LEAD(dep_utc) OVER w - arr_utc) / 3600.0, 2) AS stay_hours
    FROM flights_timeline
    WINDOW w AS (PARTITION BY passport ORDER BY dep_utc)
)
SELECT 
    passport,
    person_name,
    flight_1,
    origin_1 || ' (' || COALESCE(origin_city_1, '') || ') -> ' || 
    city_stop || ' (' || COALESCE(stop_city_name, '') || ')' AS leg_1,
    arr_utc_1,

    flight_2,
    next_origin || ' -> ' || destination_2 || ' (' || COALESCE(dest_city_2, '') || ')' AS leg_2,
    next_dep_utc AS dep_utc_2,

    stay_hours,
    ROUND(distance_leg1_km, 0) AS distance_km,

    -- Признак возврата назад (A -> B -> A)
    (city_stop = next_origin AND (origin_1 = destination_2 OR origin_city_1 = dest_city_2)) AS is_turnaround,

    -- Раздельная покупка билетов
    (pnr_1 != pnr_2) AS separate_pnr,

    -- Отсутствие сдаваемого багажа в обоих сегментах
    (baggage_1 IN ('0PC', 'None', '') AND baggage_2 IN ('0PC', 'None', '')) AS no_checked_baggage,

    baggage_1 || ' / ' || baggage_2 AS baggage_info
FROM sequenced
WHERE flight_2 IS NOT NULL
  -- Пассажир вылетает из того же аэропорта или того же города
  AND (city_stop = next_origin OR (stop_city_name IS NOT NULL AND stop_city_name = next_origin_city))
  -- Ограничение: пребывание от 45 минут до 12 часов
  AND stay_hours >= 0.75 
  AND stay_hours <= 12.0
ORDER BY 
    is_turnaround DESC,      -- Сначала прямые развороты A -> B -> A
    distance_leg1_km DESC,   -- Затем самые дальние расстояния
    stay_hours ASC;
"""

df_couriers = con.execute(query).df()

print("\n" + "=" * 100)
print(f"НАЙДЕНО ПОЛЁТОВ С ПРЕБЫВАНИЕМ <= 12 ЧАСОВ: {len(df_couriers)}")
print("=" * 100)

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 1000)

report_lines = []


def log(text=""):
    print(text)
    report_lines.append(text)


if not df_couriers.empty:
    turnarounds = df_couriers[
        df_couriers["is_turnaround"] & (df_couriers["distance_km"] >= 500)
        ]
    log(
        f"\n[!] ПРИОРИТЕТ 1: РАЗВОРОТЫ ТУДА-ОБРАТНО (A -> B -> A, расстояние >= 500 км): {len(turnarounds)}"
    )
    log("-" * 100)
    if not turnarounds.empty:
        log(
            turnarounds[
                [
                    "passport",
                    "person_name",
                    "flight_1",
                    "leg_1",
                    "stay_hours",
                    "flight_2",
                    "leg_2",
                    "distance_km",
                    "separate_pnr",
                    "no_checked_baggage",
                ]
            ]
            .head(40)
            .to_string(index=False)
        )

    freq_passports = (
        df_couriers.groupby("passport")
        .size()
        .reset_index(name="visits_count")
        .query("visits_count >= 2")
    )
    frequent_couriers = df_couriers.merge(
        freq_passports, on="passport", how="inner"
    ).sort_values(by=["visits_count", "passport"], ascending=[False, True])

    log(
        f"\n[!] ПРИОРИТЕТ 2: СЕРИЙНЫЕ «ЧЕЛНОКИ» (>= 2 экспресс-визитов за год): {len(freq_passports)} чел."
    )
    log("-" * 100)
    if not frequent_couriers.empty:
        log(
            frequent_couriers[
                [
                    "passport",
                    "person_name",
                    "visits_count",
                    "flight_1",
                    "leg_1",
                    "stay_hours",
                    "flight_2",
                    "is_turnaround",
                    "separate_pnr",
                ]
            ]
            .head(40)
            .to_string(index=False)
        )

    df_couriers.to_csv(output_csv, index=False, encoding="utf-8")
    log(f"\n[+] Полная таблица сохранена в: {output_csv}")
else:
    log("Визитов с длительностью <= 12 часов не найдено.")

with open(report_txt, "w", encoding="utf-8") as f:
    f.write("\n".join(report_lines))

log(f"[+] Текстовый отчёт сохранен в: {report_txt}")
log("=" * 100)
con.close()
