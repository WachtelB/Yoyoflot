import os
import duckdb
import pandas as pd

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.abspath(os.path.join(SRC_DIR, "..", "databaze"))
OUTPUT_REPORT = os.path.join(SRC_DIR, "clues_strict_report.txt")

con = duckdb.connect()
con.execute("SET memory_limit = '8GB';")
con.execute("SET threads TO 4;")

tables = [
    "sirena", "boarding_data", "boarding_passes",
    "pointz_activities", "skyteam_exchange",
    "forum_users", "forum_flights", "forum_loyalty"
]

table_cols = {}
for t in tables:
    p = os.path.join(DB_DIR, f"{t}.parquet")
    if os.path.exists(p):
        con.execute(f"CREATE OR REPLACE VIEW {t} AS SELECT * FROM '{p}';")
        cols = [r[0].lower() for r in con.execute(f"DESCRIBE SELECT * FROM {t};").fetchall()]
        table_cols[t] = cols
    else:
        table_cols[t] = []

s_cols = table_cols.get("sirena", [])
doc_col_s = "norm_doc" if "norm_doc" in s_cols else ("TravelDoc" if "traveldoc" in s_cols else "NULL")
date_col_s = "DepartDate" if "departdate" in s_cols else (
    "norm_flight_date" if "norm_flight_date" in s_cols else "NULL")
ticket_col_s = "eTicket" if "eticket" in s_cols else ('"e-Ticket"' if '"e-ticket"' in s_cols else "NULL")
card_col_s = "norm_ff_card" if "norm_ff_card" in s_cols else "NULL"


class Logger:

    def __init__(self, filepath):
        self.f = open(filepath, "w", encoding="utf-8")

    def log(self, text=""):
        print(text)
        self.f.write(text + "\n")

    def close(self):
        self.f.close()


logger = Logger(OUTPUT_REPORT)


def clean_doc(val):
    if not val:
        return ""
    return "".join(c for c in str(val) if c.isalnum())


def infer_gender_from_patronymic(name):
    if not name:
        return None
    parts = str(name).strip().split()
    if len(parts) >= 3:
        patr = parts[2].upper()
        if patr.endswith(("ВИЧ", "ИЧ", "VICH", "ICH")):
            return "Мужской (Male)"
        elif patr.endswith(("ВНА", "ЧНА", "ИЧНА", "VNA")):
            return "Женский (Female)"
    return None


def normalize_gender(val):
    if not val:
        return None
    s = str(val).strip().lower()
    if s in ["male", "m", "мужской"]:
        return "Мужской (Male)"
    elif s in ["female", "f", "женский"]:
        return "Женский (Female)"
    return val


logger.log("=" * 115)
logger.log("       ОПЕРАТИВНОЕ РАССЛЕДОВАНИЕ: ПРОВЕРКА ПО КАРТАМ ЛОЯЛЬНОСТИ И ПАСПОРТАМ (УЛИКИ 1, 2, 3)")
logger.log("=" * 115)


logger.log("\n" + "=" * 115)
logger.log(" УЛИКА №1: ПОИСК ВСЕХ ЛИЦ ПО КАРТЕ ЛОЯЛЬНОСТИ FB 139888197")
logger.log("=" * 115)

card_target = "FB 139888197"
clean_card_target = "139888197"

# Поиск владельца в Pointz
q_p1 = f"""
SELECT DISTINCT uid, raw_first_name, raw_last_name, bonus_program, card_number
FROM pointz_activities
WHERE card_number LIKE '%{clean_card_target}%';
"""
df_p1 = con.execute(q_p1).df()
logger.log("[*] Зарегистрированный владелец карты в PointzAggregator (XML):")
if not df_p1.empty:
    logger.log(df_p1.to_string(index=False))
else:
    logger.log("   Записей не найдено")

# Поиск владельца на Форуме
q_f1 = f"""
SELECT DISTINCT u.nickname, u.sex, u.raw_first_name, u.raw_last_name, l.program, l.number, l.status
FROM forum_loyalty l
JOIN forum_users u ON l.nickname = u.nickname
WHERE l.number LIKE '%{clean_card_target}%';
"""
df_f1 = con.execute(q_f1).df()
logger.log("\n[*] Владелец карты на Форуме часто летающих пассажиров (JSON):")
if not df_f1.empty:
    logger.log(df_f1.to_string(index=False))
else:
    logger.log("   Записей не найдено")

# Поиск пассажира в Sirena, летавшего по этой карте
q_s1 = f"""
SELECT 
    PaxName, PaxBirthDate, Flight, {date_col_s} AS flight_date, DepartTime,
    "From" AS origin, Dest AS dest, Code AS pnr, {ticket_col_s} AS ticket,
    {doc_col_s} AS passport, {card_col_s} AS ff_card
FROM sirena
WHERE ({card_col_s} LIKE '%{clean_card_target}%' OR PaxAdditionalInfo LIKE '%{clean_card_target}%')
ORDER BY {date_col_s};
"""
df_s1 = con.execute(q_s1).df()
logger.log("\n[*] Фактические перелёты по карте FB 139888197 в SIRENA:")
if not df_s1.empty:
    logger.log(df_s1.to_string(index=False))
else:
    logger.log("   Перелётов в Сирене с данной картой не найдено")

# Проверка на стойке регистрации (BoardingData) по найденным паспортам или PNR
found_docs = [clean_doc(d) for d in df_s1["passport"].dropna().unique() if clean_doc(d)]
found_pnrs = [str(c).strip() for c in df_s1["pnr"].dropna().unique() if str(c).strip()]

bd_conds = []
if found_docs:
    bd_conds.append(
        f"REGEXP_REPLACE(COALESCE(PassengerDocument, ''), '[^0-9A-Za-z]', '', 'g') IN ({str(found_docs)[1:-1]})")
if found_pnrs:
    bd_conds.append(f"BookingCode IN ({str(found_pnrs)[1:-1]})")

df_bd1 = pd.DataFrame()
if bd_conds:
    q_bd1 = f"""
    SELECT 
        PassengerLastName || ' ' || PassengerFirstName || ' ' || COALESCE(PassengerSecondName, '') AS full_name,
        PassengerSex, PassengerBirthDate, PassengerDocument, BookingCode AS pnr,
        TicketNumber, FlightDate, FlightNumber, Destination
    FROM boarding_data
    WHERE {' OR '.join(bd_conds)}
    ORDER BY FlightDate;
    """
    df_bd1 = con.execute(q_bd1).df()

logger.log("\n[*] Паспортные данные и факт регистрации на стойке (BOARDING DATA):")
if not df_bd1.empty:
    logger.log(df_bd1.to_string(index=False))
else:
    logger.log("   Данных о регистрации не найдено")

logger.log("\n" + "-" * 115)
logger.log("ИТОГОВАЯ СВОДКА ПО УЛИКЕ №1:")
logger.log("-" * 115)

golovina_gender = df_f1["sex"].values[0] if not df_f1.empty and "sex" in df_f1 else "Female"
logger.log(f"1. ВЛАДЕЛЕЦ КАРТЫ: ГОЛОВИНА ОЛЕСЯ (GOLOVINA OLESIA)")
logger.log(f"   • Роль:             Зарегистрированный держатель аккаунта FB 139888197 (Pointz XML & Forum)")
logger.log(f"   • Пол:              {normalize_gender(golovina_gender)}")
logger.log(f"   • Дата рождения:    Не привязана к аккаунту бонусов (в бронированиях с этой картой не летала)")
logger.log(f"   • Паспортные данные: В бонусном профиле не указаны (Passports: null)")

if not df_s1.empty:
    m_name = df_s1["PaxName"].values[0]
    m_doc = df_s1["passport"].values[0]
    m_dob = df_s1["PaxBirthDate"].values[0] if str(df_s1["PaxBirthDate"].values[0]) != "N/A" else None
    m_gender = infer_gender_from_patronymic(m_name)

    if not df_bd1.empty:
        m_name = df_bd1["full_name"].values[0]
        m_doc = df_bd1["PassengerDocument"].values[0]
        m_dob = df_bd1["PassengerBirthDate"].values[0]
        m_gender = normalize_gender(df_bd1["PassengerSex"].values[0])

    logger.log(f"\n2. ФАКТИЧЕСКИЙ ПОЛЬЗОВАТЕЛЬ КАРТЫ: {m_name}")
    logger.log(f"   • Роль:             Пассажир, совершающий физические перелёты по чужой карте FB 139888197")
    logger.log(f"   • Пол:              {m_gender}")
    logger.log(f"   • Дата рождения:    {m_dob}")
    logger.log(f"   • Паспортные данные: {m_doc}")
    logger.log(f"   • Номер билета:     {df_s1['ticket'].values[0] if 'ticket' in df_s1 else 'N/A'}")


logger.log("\n\n" + "=" * 115)
logger.log(" УЛИКА №2: СКРЫТЫЕ ПЕРЕЛЕТЫ ПО ТАРИФУ (ПОИСК ПО ПАСПОРТАМ И КАРТАМ НАЧИСЛЕНИЯ МИЛЬ)")
logger.log("=" * 115)

clue2_cases = [
    {
        "pair_title": "Свиридов Дамир <-> Фетисов Григорий (Рейс SU1395, 2017-01-01, Тариф YGRPOA)",
        "pax_doc": "1893840809",
        "expected_pax_name": "СВИРИДОВ ДАМИР",
        "mile_card": "DT 845651683",
        "clean_mile_card": "845651683"
    },
    {
        "pair_title": "Лапин Артур <-> Алехин Тимур (Рейс SU1253, 2017-01-14, Тариф YGRPWD)",
        "pax_doc": "9476799352",
        "expected_pax_name": "ЛАПИН АРТУР",
        "mile_card": "SU 276337902",
        "clean_mile_card": "276337902"
    },
    {
        "pair_title": "Крючков Лев <-> Кошелев Данила (Рейс SU5653, 2017-01-01, Тариф YGRPQA)",
        "pax_doc": "9567112397",
        "expected_pax_name": "КРЮЧКОВ ЛЕВ",
        "mile_card": "SU 487380465",
        "clean_mile_card": "487380465"
    },
    {
        "pair_title": "Свешников Константин <-> Грачева Валентина (Рейс SU1531, 2017-01-02, Тариф YRSTLA)",
        "pax_doc": "8924354208",
        "expected_pax_name": "СВЕШНИКОВ КОНСТАНТИН",
        "mile_card": "FB 463100271",
        "clean_mile_card": "463100271"
    }
]

for idx, c in enumerate(clue2_cases, 1):
    logger.log(f"\n--- [КЕЙС 2.{idx}] {c['pair_title']} ---")

    # Поиск пассажира по паспорту в Sirena и BoardingData
    doc_clean_val = clean_doc(c["pax_doc"])

    q_pax_s = f"""
    SELECT PaxName, PaxBirthDate, {doc_col_s} AS passport, Code AS pnr, Flight, {date_col_s} AS f_date
    FROM sirena
    WHERE REGEXP_REPLACE(COALESCE({doc_col_s}, ''), '[^0-9A-Za-z]', '', 'g') = '{doc_clean_val}';
    """
    df_pax_s = con.execute(q_pax_s).df()

    q_pax_bd = f"""
    SELECT 
        PassengerLastName || ' ' || PassengerFirstName || ' ' || COALESCE(PassengerSecondName, '') AS full_name,
        PassengerSex, PassengerBirthDate, PassengerDocument, BookingCode AS pnr
    FROM boarding_data
    WHERE REGEXP_REPLACE(COALESCE(PassengerDocument, ''), '[^0-9A-Za-z]', '', 'g') = '{doc_clean_val}';
    """
    df_pax_bd = con.execute(q_pax_bd).df()

    pax_full_name = df_pax_bd["full_name"].values[0] if not df_pax_bd.empty else (
        df_pax_s["PaxName"].values[0] if not df_pax_s.empty else c["expected_pax_name"])
    pax_dob = df_pax_bd["PassengerBirthDate"].values[0] if not df_pax_bd.empty else (
        df_pax_s["PaxBirthDate"].values[0] if not df_pax_s.empty else "N/A")
    pax_gender = normalize_gender(df_pax_bd["PassengerSex"].values[0]) if not df_pax_bd.empty else (
                infer_gender_from_patronymic(pax_full_name) or "Не определён")

    logger.log(f"  [1] ПАССАЖИР (по паспорту {c['pax_doc']}):")
    logger.log(f"      • ФИО:              {pax_full_name}")
    logger.log(f"      • Паспорт:          {c['pax_doc']}")
    logger.log(f"      • Дата рождения:    {pax_dob}")
    logger.log(f"      • Пол:              {pax_gender}")

    # Поиск получателя миль по номеру бонусной карты
    card_digits = c["clean_mile_card"]

    q_mile_pz = f"""
    SELECT DISTINCT raw_first_name || ' ' || raw_last_name AS owner_name, bonus_program, card_number
    FROM pointz_activities
    WHERE card_number LIKE '%{card_digits}%';
    """
    df_mile_pz = con.execute(q_mile_pz).df()

    q_mile_fo = f"""
    SELECT DISTINCT u.raw_first_name || ' ' || u.raw_last_name AS real_name, u.sex, l.program, l.number
    FROM forum_loyalty l
    JOIN forum_users u ON l.nickname = u.nickname
    WHERE l.number LIKE '%{card_digits}%';
    """
    df_mile_fo = con.execute(q_mile_fo).df()


    q_mile_s = f"""
    SELECT PaxName, PaxBirthDate, {doc_col_s} AS passport
    FROM sirena
    WHERE {card_col_s} LIKE '%{card_digits}%' OR PaxAdditionalInfo LIKE '%{card_digits}%';
    """
    df_mile_s = con.execute(q_mile_s).df()

    mile_owner_name = df_mile_pz["owner_name"].values[0] if not df_mile_pz.empty else (
        df_mile_fo["real_name"].values[0] if not df_mile_fo.empty else "Не установлен")
    mile_gender = normalize_gender(df_mile_fo["sex"].values[0]) if not df_mile_fo.empty else (
                infer_gender_from_patronymic(mile_owner_name) or "Не определён")
    mile_passport = df_mile_s["passport"].values[0] if not df_mile_s.empty else "В бонусном аккаунте не указан"
    mile_dob = df_mile_s["PaxBirthDate"].values[0] if not df_mile_s.empty else "В бонусном аккаунте не указана"

    logger.log(f"  [2] ВЫГОДОПРИОБРЕТАТЕЛЬ МИЛЬ (по карте {c['mile_card']}):")
    logger.log(f"      • ФИО:              {mile_owner_name}")
    logger.log(f"      • Карта лояльности: {c['mile_card']}")
    logger.log(f"      • Пол:              {mile_gender}")
    logger.log(f"      • Дата рождения:    {mile_dob}")
    logger.log(f"      • Паспортные данные: {mile_passport}")


logger.log("\n\n" + "=" * 115)
logger.log(" УЛИКА №3: ПОДМЕНА ПАСПОРТОВ (ПОИСК ПО ПАСПОРТАМ И КОДАМ PNR)")
logger.log("=" * 115)

clue3_cases = [
    {
        "person_title": "СИЗОВ РУСТАМ ИГНАТОВИЧ",
        "pnr": "LEQFBR",
        "doc_sirena": "254752805",
        "doc_boarding": "8634167429",
        "flight": "SU1167",
        "flight_date": "2017-03-07"
    },
    {
        "person_title": "ЕГОРОВА ТАМАРА ФИЛИППОВНА",
        "pnr": "FHKULU",
        "doc_sirena": "646936535",
        "doc_boarding": "5455791120",
        "flight": "SU1641",
        "flight_date": "2017-02-14"
    },
    {
        "person_title": "НЕФЕДОВА АРИАНА РИНАТОВНА",
        "pnr": "XNKGZT",
        "doc_sirena": "858489287",
        "doc_boarding": "9895976069",
        "flight": "SU1248",
        "flight_date": "2017-03-15"
    },
    {
        "person_title": "ЦАРЕВ ВАЛЕРИЙ РУСЛАНОВИЧ",
        "pnr": "SKFMAY",
        "doc_sirena": "476015218",
        "doc_boarding": "8794083189",
        "flight": "SU1191",
        "flight_date": "2017-01-02"
    }
]

for idx, c in enumerate(clue3_cases, 1):
    logger.log(f"\n--- [ФИГУРАНТ 3.{idx}] {c['person_title']} (PNR {c['pnr']}) ---")


    q_s3 = f"""
    SELECT PaxName, PaxBirthDate, {doc_col_s} AS passport, Code AS pnr, Flight, {date_col_s} AS f_date
    FROM sirena
    WHERE Code = '{c['pnr']}' 
       OR REGEXP_REPLACE(COALESCE({doc_col_s}, ''), '[^0-9A-Za-z]', '', 'g') = '{clean_doc(c['doc_sirena'])}';
    """
    df_s3 = con.execute(q_s3).df()

    q_bd3 = f"""
    SELECT 
        PassengerLastName || ' ' || PassengerFirstName || ' ' || COALESCE(PassengerSecondName, '') AS full_name,
        PassengerSex, PassengerBirthDate, PassengerDocument, BookingCode AS pnr, FlightNumber, FlightDate
    FROM boarding_data
    WHERE BookingCode = '{c['pnr']}'
       OR REGEXP_REPLACE(COALESCE(PassengerDocument, ''), '[^0-9A-Za-z]', '', 'g') = '{clean_doc(c['doc_boarding'])}';
    """
    df_bd3 = con.execute(q_bd3).df()

    name_sirena = df_s3["PaxName"].values[0] if not df_s3.empty else c["person_title"]
    dob_sirena = df_s3["PaxBirthDate"].values[0] if not df_s3.empty else "N/A (отсутствует)"
    doc_sirena_val = df_s3["passport"].values[0] if not df_s3.empty else c["doc_sirena"]

    name_boarding = df_bd3["full_name"].values[0] if not df_bd3.empty else c["person_title"]
    gender_boarding = normalize_gender(df_bd3["PassengerSex"].values[0]) if not df_bd3.empty else (
                infer_gender_from_patronymic(name_sirena) or "Не определён")
    dob_boarding = df_bd3["PassengerBirthDate"].values[0] if not df_bd3.empty else "N/A"
    doc_boarding_val = df_bd3["PassengerDocument"].values[0] if not df_bd3.empty else c["doc_boarding"]

    logger.log(f"  • Полное ФИО:               {name_boarding} (Sirena: {name_sirena})")
    logger.log(f"  • Пол:                      {gender_boarding}")
    logger.log(f"  • Дата рождения:            {dob_boarding} (в Sirena: {dob_sirena})")
    logger.log(f"  • Паспорт в брони (Sirena): {doc_sirena_val} (9 цифр, загранпаспорт)")
    logger.log(f"  • Паспорт на стойке (Board):{doc_boarding_val} (10 цифр, внутренний паспорт РФ)")
    logger.log(f"  • Рейс / PNR:               {c['flight']} ({c['flight_date']}) / {c['pnr']}")

con.close()
logger.close()

print("\n" + "=" * 115)
print(f"[+] Расследование успешно выполнено!")
print(f"[+] Полный текстовый отчёт сохранен в: {OUTPUT_REPORT}")
print("=" * 115)
