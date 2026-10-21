"""Пользователи, у которых число рейсов в один город превышает порог."""

from pathlib import Path

import duckdb


FLIGHT_THRESHOLD = 7

PROJECT_DIR = Path(__file__).resolve().parents[2]
DATABASE = PROJECT_DIR / 'databaze' / 'yoyoflot.duckdb'
FLIGHTS_SQL = Path(__file__).with_name('passenger_flights.sql')


def find_frequent_destinations(connection, threshold):
    """Возвращает имя, город и рейсы с датами и багажом для пар выше порога."""
    flights_sql = FLIGHTS_SQL.read_text(encoding='utf-8').strip().rstrip(';')

    sql = f"""
        SELECT
            passenger_name,
            destination,
            LIST(
                STRUCT_PACK(flight_date := flight_date, baggage := baggage)
                ORDER BY flight_date NULLS LAST, flight, baggage
            ) AS flight_details
        FROM (
            {flights_sql}
        ) AS flights
        WHERE passenger_name IS NOT NULL
          AND destination IS NOT NULL
        GROUP BY passenger_name, destination
        HAVING COUNT(*) > ?
        ORDER BY passenger_name, COUNT(*) DESC, destination
    """

    return connection.execute(sql, [threshold]).fetchall()


if __name__ == '__main__':
    try:
        connection = duckdb.connect(str(DATABASE), read_only=True)
    except duckdb.IOException as error:
        raise SystemExit(
            f'Не удалось открыть базу: {error}\n'
            'Закрой приложение, которое использует файл базы, и повтори запуск.\n'
            'Закрытие вкладки браузера не освобождает базу.'
        )

    with connection:
        results = find_frequent_destinations(connection, FLIGHT_THRESHOLD)

    print(f'Пользователи с числом рейсов в один город больше {FLIGHT_THRESHOLD}:')
    print('Имя | Город | Даты рейсов и багаж')

    for name, city, flights in results:
        entries = []
        for flight in flights:
            date = flight['flight_date']
            baggage = flight['baggage']
            date_text = date.isoformat() if date is not None else 'дата неизвестна'
            baggage_text = baggage if baggage is not None else 'нет данных'
            entries.append(f'{date_text} (багаж: {baggage_text})')

        print(f'{name} | {city} | {", ".join(entries)}')

    if not results:
        print('Совпадений нет.')
