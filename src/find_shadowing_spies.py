import os
import duckdb
import pandas as pd

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.abspath(os.path.join(SRC_DIR, "..", "databaze"))
sirena_parquet = os.path.join(DB_DIR, "sirena.parquet")
output_csv = os.path.join(SRC_DIR, "shadowing_pairs.csv")
report_txt = os.path.join(SRC_DIR, "shadowing_report.txt")

print("=" * 100)
print("             ПОИСК ШПИОНОВ: ПАТТЕРН «ТЕНЬ» (СОВМЕСТНЫЕ РЕЙСЫ НА РАЗНЫХ PNR)")
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
date_col = "norm_flight_date" if "norm_flight_date" in sirena_cols else "DepartDate"

print(f"[*] Колонка паспорта: {doc_col}")
print(f"[*] Колонка даты:     {date_col}")

print("[*] Анализ перелётов и поиск скрытых спутников...")

query = f"""
WITH base_flights AS (
    SELECT 
        {doc_col} AS doc,
        TRIM(PaxName) AS pax_name,
        -- Извлекаем первое слово как фамилию для проверки родства
        UPPER(SPLIT_PART(TRIM(PaxName), ' ', 1)) AS surname,
        Flight AS flight_no,
        {date_col} AS flight_date,
        UPPER(TRIM("From")) AS origin,
        UPPER(TRIM(Dest)) AS destination,
        TRIM(Code) AS pnr,
        -- Уникальный идентификатор физического борта
        Flight || '_' || {date_col} AS flight_instance
    FROM '{sirena_parquet}'
    WHERE {doc_col} IS NOT NULL AND {doc_col} != ''
      AND Flight IS NOT NULL AND {date_col} IS NOT NULL
      AND Code IS NOT NULL AND TRIM(Code) != ''
),

-- Оставляем только часто летающих пассажиров (>= 3 полетов)
frequent_passengers AS (
    SELECT doc
    FROM base_flights
    GROUP BY doc
    HAVING COUNT(DISTINCT flight_instance) >= 3
),

filtered_flights AS (
    SELECT bf.*
    FROM base_flights bf
    JOIN frequent_passengers fp ON bf.doc = fp.doc
),

-- Сопоставляем пассажиров на одном и том же рейсе (doc_1 < doc_2 исключает дубли)
shared_flights AS (
    SELECT 
        f1.doc AS doc_1,
        f1.pax_name AS name_1,
        f1.surname AS surname_1,
        f1.pnr AS pnr_1,
        f2.doc AS doc_2,
        f2.pax_name AS name_2,
        f2.surname AS surname_2,
        f2.pnr AS pnr_2,
        f1.flight_instance,
        f1.flight_no,
        f1.flight_date,
        f1.origin || '->' || f1.destination AS route
    FROM filtered_flights f1
    JOIN filtered_flights f2 
      ON f1.flight_instance = f2.flight_instance
     AND f1.doc < f2.doc
)

SELECT 
    doc_1 AS passport_1,
    name_1,
    doc_2 AS passport_2,
    name_2,
    (surname_1 = surname_2) AS same_surname,
    -- Число совместных рейсов с РАЗНЫМИ бронированиями
    COUNT(DISTINCT CASE WHEN pnr_1 != pnr_2 THEN flight_instance END) AS shared_flights_count,
    -- Список рейсов
    STRING_AGG(DISTINCT flight_no || ' (' || flight_date || ', ' || route || ')', ' | ') AS flights_list,
    -- Использованные коды PNR
    STRING_AGG(DISTINCT pnr_1 || ' vs ' || pnr_2, ' ; ') AS pnr_pairs
FROM shared_flights
GROUP BY doc_1, name_1, surname_1, doc_2, name_2, surname_2
HAVING 
    -- Не менее 3 совместных перелётов на РАЗНЫХ PNR
    COUNT(DISTINCT CASE WHEN pnr_1 != pnr_2 THEN flight_instance END) >= 3
    -- И они НИ РАЗУ не были в одной брони (исключаем семьи и официальные группы)
    AND COUNT(DISTINCT CASE WHEN pnr_1 = pnr_2 THEN flight_instance END) = 0
ORDER BY shared_flights_count DESC;
"""

df_pairs = con.execute(query).df()

print("\n" + "=" * 100)
print(f"НАЙДЕНО ПОДОЗРИТЕЛЬНЫХ ПАР (>= 3 СОВМЕСТНЫХ РЕЙСОВ, РАЗНЫЕ PNR): {len(df_pairs)}")
print("=" * 100)

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 1000)

report_lines = []


def log(text=""):
    print(text)
    report_lines.append(text)


if not df_pairs.empty:
    diff_surnames = df_pairs[~df_pairs["same_surname"]]
    same_surnames = df_pairs[df_pairs["same_surname"]]

    log(
        f"\n[!] ПРИОРИТЕТ 1: РАЗНЫЕ ФАМИЛИИ (Скрытое сопровождение / агентурная пара): {len(diff_surnames)}"
    )
    log("-" * 100)
    if not diff_surnames.empty:
        log(
            diff_surnames[
                [
                    "passport_1",
                    "name_1",
                    "passport_2",
                    "name_2",
                    "shared_flights_count",
                    "flights_list",
                ]
            ].to_string(index=False)
        )

    if not same_surnames.empty:
        log(
            f"\n[?] ПРИОРИТЕТ 2: ОДИНАКОВЫЕ ФАМИЛИИ (Возможно родственники на раздельных билетах): {len(same_surnames)}"
        )
        log("-" * 100)
        log(
            same_surnames[
                [
                    "passport_1",
                    "name_1",
                    "passport_2",
                    "name_2",
                    "shared_flights_count",
                ]
            ].to_string(index=False)
        )

    # Сохраняем в CSV
    df_pairs.to_csv(output_csv, index=False, encoding="utf-8")
    log(f"\n[+] Полная таблица сохранена в: {output_csv}")
else:
    log("Подозрительных пар с >= 3 совместными рейсами не обнаружено.")

with open(report_txt, "w", encoding="utf-8") as f:
    f.write("\n".join(report_lines))

log(f"[+] Текстовый отчёт сохранен в: {report_txt}")
log("=" * 100)
con.close()
