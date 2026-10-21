import os
import duckdb
import pandas as pd

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.abspath(os.path.join(SRC_DIR, "..", "databaze"))
AIRPORTS_CSV = os.path.join(SRC_DIR, "airports_reference.csv")
OUTPUT_FILE = os.path.join(SRC_DIR, "clue3_routes_report.txt")

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 1000)

con = duckdb.connect()
con.execute("SET memory_limit = '4GB';")

con.execute(f"""
    CREATE OR REPLACE TABLE airports AS 
    SELECT iata, city, country 
    FROM read_csv_auto('{AIRPORTS_CSV}');

    CREATE OR REPLACE VIEW sirena AS 
    SELECT * FROM '{os.path.join(DB_DIR, "sirena.parquet")}';

    CREATE OR REPLACE VIEW passes AS 
    SELECT * FROM '{os.path.join(DB_DIR, "boarding_passes.parquet")}';
""")

sirena_cols = [
    r[0].lower() for r in con.execute("DESCRIBE SELECT * FROM sirena;").fetchall()
]
date_col = (
    "DepartDate"
    if "departdate" in sirena_cols
    else ("norm_flight_date" if "norm_flight_date" in sirena_cols else "NULL")
)
doc_col = (
    "norm_doc"
    if "norm_doc" in sirena_cols
    else ("TravelDoc" if "traveldoc" in sirena_cols else "NULL")
)

targets_data = [
    (
        "3.1",
        "СИЗОВ РУСТАМ ИГНАТОВИЧ",
        "SIZOV RUSTAM IGNATOVICH",
        "SU1167",
        "2017-03-07",
        "LEQFBR",
    ),
    (
        "3.2",
        "ЕГОРОВА ТАМАРА ФИЛИППОВНА",
        "EGOROVA TAMARA FILIPPOVNA",
        "SU1641",
        "2017-02-14",
        "FHKULU",
    ),
    (
        "3.3",
        "НЕФЕДОВА АРИАНА РИНАТОВНА",
        "NEFEDOVA ARIANA R.",
        "SU1248",
        "2017-03-15",
        "XNKGZT",
    ),
    (
        "3.4",
        "ЦАРЕВ ВАЛЕРИЙ РУСЛАНОВИЧ",
        "TSAREV VALERII R.",
        "SU1191",
        "2017-01-02",
        "SKFMAY",
    ),
]

targets_df = pd.DataFrame(
    targets_data,
    columns=["num", "name_ru", "name_en", "flight_no", "flight_date", "pnr"],
)
con.register("targets", targets_df)

query = f"""
WITH routes_sirena AS (
    SELECT 
        t.num,
        t.name_ru,
        t.name_en,
        t.flight_no,
        t.flight_date,
        t.pnr,
        s.From AS from_iata,
        COALESCE(a_from.city, 'Unknown') AS from_city,
        COALESCE(a_from.country, '') AS from_country,
        s.Dest AS to_iata,
        COALESCE(a_to.city, 'Unknown') AS to_city,
        COALESCE(a_to.country, '') AS to_country,
        s.DepartTime AS dep_time,
        s.ArrivalTime AS arr_time,
        s.{doc_col} AS passport_sirena
    FROM targets t
    LEFT JOIN sirena s 
      ON (s.Code = t.pnr OR (s.Flight = t.flight_no AND s.{date_col} = t.flight_date))
    LEFT JOIN airports a_from ON s.From = a_from.iata
    LEFT JOIN airports a_to ON s.Dest = a_to.iata
),
routes_passes AS (
    SELECT 
        p.pnr,
        p.from_iata,
        p.from_city,
        p.to_iata,
        p.to_city,
        p.flight_time
    FROM passes p
    WHERE p.pnr IN (SELECT pnr FROM targets)
)
SELECT 
    r.num,
    r.name_ru,
    r.name_en,
    r.flight_no,
    r.flight_date,
    r.pnr,
    COALESCE(r.from_iata, p.from_iata) AS origin_iata,
    COALESCE(r.from_city, p.from_city) AS origin_city,
    COALESCE(r.to_iata, p.to_iata) AS dest_iata,
    COALESCE(r.to_city, p.to_city) AS dest_city,
    r.dep_time,
    r.arr_time
FROM routes_sirena r
LEFT JOIN routes_passes p ON r.pnr = p.pnr
ORDER BY r.num;
"""

df_routes = con.execute(query).df().drop_duplicates(subset=["num", "pnr"])

output_lines = []


def log(text=""):
    print(text)
    output_lines.append(text)


log("=" * 115)
log("       МАРШРУТЫ, АЭРОПОРТЫ И ГОРОДА ДЛЯ ФИГУРАНТОВ УЛИКИ №3 (ПОДМЕНА ПАСПОРТОВ)")
log("=" * 115)

for _, r in df_routes.iterrows():
    log(f"\n[ФИГУРАНТ {r['num']}] {r['name_ru']} ({r['name_en']})")
    log(f"  • Рейс и дата:           {r['flight_no']} ({r['flight_date']})")
    log(f"  • Код брони (PNR):       {r['pnr']}")
    log(
        f"  • Отправление (FROM):    {r['origin_iata']} — {r['origin_city']} (вылет: {r['dep_time'] if pd.notna(r['dep_time']) else 'Н/Д'})"
    )
    log(
        f"  • Прибытие (TO):         {r['dest_iata']} — {r['dest_city']} (посадка: {r['arr_time'] if pd.notna(r['arr_time']) else 'Н/Д'})"
    )
    log(
        f"  • Полный маршрут:        {r['origin_city']} ({r['origin_iata']}) -> {r['dest_city']} ({r['dest_iata']})"
    )
    log("-" * 115)

log("\n" + "=" * 115)
log("СВОДНАЯ ТАБЛИЦА МАРШРУТОВ:")
log("=" * 115)
log(
    df_routes[
        [
            "num",
            "name_ru",
            "flight_no",
            "flight_date",
            "pnr",
            "origin_iata",
            "origin_city",
            "dest_iata",
            "dest_city",
        ]
    ].to_string(index=False)
)


with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(output_lines))

log(f"\n[+] Отчет сохранен в файл: {OUTPUT_FILE}")
log("=" * 115)

con.close()
