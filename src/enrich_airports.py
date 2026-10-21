import os
import urllib.error
import urllib.request
import pandas as pd

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_CSV = os.path.join(SRC_DIR, "airports_extracted.csv")
OUTPUT_CSV = os.path.join(SRC_DIR, "airports_reference.csv")
OPENFLIGHTS_FILE = os.path.join(SRC_DIR, "airports_openflights.dat")
OPENFLIGHTS_URL = (
    "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat"
)


AIRPORT_OVERRIDES = {
    "REA": {
        "city": "SEOUL",
        "country": "South Korea",
        "timezone": "Asia/Seoul",
        "lat": 37.4602,
        "lon": 126.4407,
    },
    "MOW": {
        "city": "MOSCOW",
        "country": "Russia",
        "timezone": "Europe/Moscow",
        "lat": 55.7558,
        "lon": 37.6173,
    },
    "PAR": {
        "city": "PARIS",
        "country": "France",
        "timezone": "Europe/Paris",
        "lat": 49.0097,
        "lon": 2.5479,
    },
    "ROM": {
        "city": "ROME",
        "country": "Italy",
        "timezone": "Europe/Rome",
        "lat": 41.8003,
        "lon": 12.2389,
    },
    "BJS": {
        "city": "BEIJING",
        "country": "China",
        "timezone": "Asia/Shanghai",
        "lat": 40.0799,
        "lon": 116.6031,
    },
}

print("[*] Шаг 2: Обогащение аэропортов координатами и часовыми поясами...")

if not os.path.exists(INPUT_CSV):
    raise FileNotFoundError(
        f"Файл {INPUT_CSV} не найден! Сначала выполните extract_airports.py."
    )

df_extracted = pd.read_csv(INPUT_CSV)
print(f"[*] Загружено извлеченных аэропортов: {len(df_extracted)}")

if not os.path.exists(OPENFLIGHTS_FILE):
    print(f"[*] Скачивание справочника OpenFlights с GitHub...")
    try:
        urllib.request.urlretrieve(OPENFLIGHTS_URL, OPENFLIGHTS_FILE)
        print(f"[+] База OpenFlights успешно скачана: {OPENFLIGHTS_FILE}")
    except Exception as e:
        print(f"[!] Ошибка скачивания OpenFlights: {e}")

if os.path.exists(OPENFLIGHTS_FILE):
    cols = [
        "airport_id",
        "name",
        "of_city",
        "of_country",
        "iata",
        "icao",
        "lat",
        "lon",
        "alt",
        "tz_offset",
        "dst",
        "tz_name",
        "type",
        "source",
    ]

    df_of = pd.read_csv(
        OPENFLIGHTS_FILE,
        names=cols,
        na_values=["\\N", "", "NaN"],
        keep_default_na=True,
        on_bad_lines="skip",
    )

    # Очищаем IATA: только 3 латинские буквы
    df_of = df_of[df_of["iata"].notna()]
    df_of["iata"] = df_of["iata"].astype(str).str.strip().str.upper()
    df_of = df_of[df_of["iata"].str.len() == 3]

    # Сортируем так, чтобы коммерческие аэропорты шли первыми, и дедуплицируем по IATA
    df_of["is_airport"] = df_of["type"].str.lower() == "airport"
    df_of = df_of.sort_values(
        by=["is_airport", "airport_id"], ascending=[False, True]
    )
    df_of = df_of.drop_duplicates(subset=["iata"], keep="first")

    ref_data = df_of[
        ["iata", "of_city", "of_country", "lat", "lon", "tz_name"]
    ].copy()
else:
    print(
        "[!] Локальный справочник OpenFlights отсутствует. Используются только ручные переопределения."
    )
    ref_data = pd.DataFrame(
        columns=["iata", "of_city", "of_country", "lat", "lon", "tz_name"]
    )

merged = df_extracted.merge(ref_data, on="iata", how="left")

merged["city"] = merged["city"].fillna(merged["of_city"])
merged["country"] = merged["of_country"]
merged = merged.rename(columns={"tz_name": "timezone"})


overrides_applied = 0
for iata_code, data in AIRPORT_OVERRIDES.items():
    mask = merged["iata"] == iata_code
    if mask.any():
        for field, val in data.items():
            merged.loc[mask, field] = val
        overrides_applied += 1


missing_coords = merged[merged["lat"].isna() | merged["lon"].isna()]
missing_tz = merged[merged["timezone"].isna() | (merged["timezone"] == "")]

print("\n" + "=" * 80)
print("                    ОТЧЕТ ПО ОБОГАЩЕНИЮ АЭРОПОРТОВ")
print("=" * 80)
print(f"Всего аэропортов в датасете:           {len(merged)}")
print(f"Успешно сопоставлено с OpenFlights:   {len(merged) - len(missing_coords)}")
print(f"Применено ручных исправлений (fixes):  {overrides_applied}")
print(f"Осталось без координат (lat/lon):     {len(missing_coords)}")
print(f"Осталось без таймзоны:                {len(missing_tz)}")

if not missing_coords.empty:
    print("\n[!] Список аэропортов без координат (первые 15):")
    print(
        missing_coords[["iata", "city", "total_occurrences"]]
        .head(15)
        .to_string(index=False)
    )

merged["timezone"] = merged["timezone"].fillna("UTC")

final_columns = [
    "iata",
    "city",
    "country",
    "lat",
    "lon",
    "timezone",
    "total_occurrences",
]
merged = merged[final_columns]


merged.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
print(f"\n[+] Итоговый справочник успешно сохранен в: {OUTPUT_CSV}")
print("=" * 80)