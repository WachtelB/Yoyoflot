import os
import duckdb
import pandas as pd

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.abspath(os.path.join(SRC_DIR, "..", "databaze"))

passes_parquet = os.path.join(DB_DIR, "boarding_passes.parquet")
forum_parquet = os.path.join(DB_DIR, "forum_flights.parquet")
sirena_parquet = os.path.join(DB_DIR, "sirena.parquet")
output_file = os.path.join(SRC_DIR, "airports_extracted.csv")

print("[*] Шаг 1: Извлечение пар Аэропорт (IATA) - Город...")
print(f"[*] Путь к Parquet-файлам: {DB_DIR}")

con = duckdb.connect()
con.execute("SET memory_limit = '4GB';")

query = f"""
WITH raw_pairs AS (
    -- 1. Из посадочных талонов (отправление)
    SELECT 
        UPPER(TRIM(from_iata)) AS iata,
        UPPER(TRIM(from_city)) AS city
    FROM '{passes_parquet}'
    WHERE from_iata IS NOT NULL AND TRIM(from_iata) != ''

    UNION ALL

    -- Из посадочных талонов (прибытие)
    SELECT 
        UPPER(TRIM(to_iata)) AS iata,
        UPPER(TRIM(to_city)) AS city
    FROM '{passes_parquet}'
    WHERE to_iata IS NOT NULL AND TRIM(to_iata) != ''

    UNION ALL

    -- 2. Из перелетов с форума (только iata и city, без country)
    SELECT 
        UPPER(TRIM(from_iata)) AS iata,
        UPPER(TRIM(from_city)) AS city
    FROM '{forum_parquet}'
    WHERE from_iata IS NOT NULL AND TRIM(from_iata) != ''

    UNION ALL

    -- Из перелетов с форума (прибытие)
    SELECT 
        UPPER(TRIM(to_iata)) AS iata,
        UPPER(TRIM(to_city)) AS city
    FROM '{forum_parquet}'
    WHERE to_iata IS NOT NULL AND TRIM(to_iata) != ''

    UNION ALL

    -- 3. Из Сирены (только коды, чтобы не потерять аэропорты)
    SELECT UPPER(TRIM("From")) AS iata, NULL AS city 
    FROM '{sirena_parquet}' WHERE "From" IS NOT NULL

    UNION ALL

    SELECT UPPER(TRIM(Dest)) AS iata, NULL AS city 
    FROM '{sirena_parquet}' WHERE Dest IS NOT NULL
)
SELECT 
    iata,
    MODE(city) AS city,       -- Самый частый вариант названия города
    COUNT(*) AS total_occurrences
FROM raw_pairs
WHERE LENGTH(iata) = 3        -- Валидные 3-буквенные IATA коды
  AND REGEXP_MATCHES(iata, '^[A-Z]{{3}}$')
GROUP BY iata
ORDER BY total_occurrences DESC;
"""

df_airports = con.execute(query).df()
df_airports.to_csv(output_file, index=False, encoding="utf-8")

print(f"[+] Успешно извлечено {len(df_airports)} уникальных IATA-кодов.")
print(f"[+] Результат сохранен в: {output_file}")
con.close()
