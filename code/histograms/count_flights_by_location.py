"""Количество уникальных рейсов в/из каждого города и аэропорта."""

import csv
from pathlib import Path

import duckdb


BOTTOM_N = 7

PROJECT_DIR = Path(__file__).resolve().parents[2]
DATABASE = PROJECT_DIR / 'databaze' / 'yoyoflot.duckdb'
SQL_FILE = Path(__file__).with_name('flight_locations.sql')
PASSENGERS_SQL = Path(__file__).with_name('passengers_by_destination.sql')
OUTPUT_DIR = Path(__file__).parent / 'results' / 'flights_by_location'


def count_flights_by_location(connection, bottom_n=None):
    """По bottom_n самых редких мест в каждой категории и полный список расхождений."""
    sql = SQL_FILE.read_text(encoding='utf-8').strip().rstrip(';')

    connection.execute(f'CREATE OR REPLACE TEMP TABLE location_flights AS {sql}')

    counts = connection.execute('''
        SELECT location_type, direction, location, COUNT(*) AS flight_count
        FROM location_flights
        GROUP BY location_type, direction, location
        -- Нумеруем места от самых редких отдельно в каждой из четырёх категорий.
        QUALIFY CAST(? AS BIGINT) IS NULL OR ROW_NUMBER() OVER (
            PARTITION BY location_type, direction
            ORDER BY flight_count ASC, location
        ) <= CAST(? AS BIGINT)
        ORDER BY location_type, direction, flight_count ASC, location
    ''', [bottom_n, bottom_n]).fetchall()

    conflicts = connection.execute('''
        SELECT location_type, direction, flight_number, flight_date,
               STRING_AGG(location, ' | ' ORDER BY location) AS locations
        FROM location_flights
        GROUP BY location_type, direction, flight_number, flight_date
        HAVING COUNT(*) > 1
        ORDER BY location_type, direction, flight_date, flight_number
    ''').fetchall()

    return counts, conflicts


def find_destination_passengers(connection, counts):
    """Имена и рейсы для выбранных городов и аэропортов прибытия."""
    destinations = [
        (kind, location)
        for kind, direction, location, count in counts
        if direction == 'arrival'
    ]
    connection.execute('''
        CREATE OR REPLACE TEMP TABLE selected_destinations (
            location_type VARCHAR, location VARCHAR
        )
    ''')
    if not destinations:
        return []
    connection.executemany('INSERT INTO selected_destinations VALUES (?, ?)', destinations)
    return connection.execute(PASSENGERS_SQL.read_text(encoding='utf-8')).fetchall()


def save_csv(filename, headers, rows):
    with (OUTPUT_DIR / filename).open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.writer(file, delimiter=';')
        writer.writerow(headers)
        writer.writerows(rows)


if __name__ == '__main__':
    try:
        connection = duckdb.connect(str(DATABASE), read_only=True)
    except duckdb.IOException as error:
        raise SystemExit(
            f'Не удалось открыть базу: {error}\n'
            'Закрой приложение, которое использует файл базы, и повтори запуск.'
        )

    with connection:
        counts, conflicts = count_flights_by_location(connection, BOTTOM_N)
        passengers = find_destination_passengers(connection, counts)

    print(f'По {BOTTOM_N} мест с наименьшим числом рейсов в каждой категории.'
          if BOTTOM_N is not None else 'Все места, начиная с самых редких.')

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    reports = [
        ('city', 'departure', 'city_departures.csv', 'Вылеты из городов'),
        ('city', 'arrival', 'city_arrivals.csv', 'Прилёты в города'),
        ('airport', 'departure', 'airport_departures.csv', 'Вылеты из аэропортов'),
        ('airport', 'arrival', 'airport_arrivals.csv', 'Прилёты в аэропорты'),
    ]

    for location_type, direction, filename, title in reports:
        rows = [
            (location, count)
            for kind, way, location, count in counts
            if kind == location_type and way == direction
        ]
        save_csv(filename, ['location', 'flight_count'], rows)
        print(f'\n{title}:')
        for location, count in rows:
            print(f'{location}: {count}')
            if direction == 'arrival':
                names = sorted({
                    name for kind, place, flight, date, name, source, basis in passengers
                    if kind == location_type and place == location and name is not None
                })
                print('  Пассажиры: ' + (', '.join(names) if names else 'имена не найдены'))
                if any(kind == location_type and place == location and name is None
                       for kind, place, flight, date, name, source, basis in passengers):
                    print('  Есть также записи без установленного имени.')

    save_csv(
        'destination_passengers.csv',
        ['location_type', 'location', 'flight_number', 'flight_date',
         'passenger_name', 'source', 'name_basis'],
        passengers,
    )

    save_csv(
        'location_conflicts.csv',
        ['location_type', 'direction', 'flight_number', 'flight_date', 'locations'],
        conflicts,
    )
    print(f'\nСочетаний «рейс + дата + тип места + направление» с разными местами: {len(conflicts)}')
    print('Такие рейсы учтены один раз в каждом указанном месте; см. location_conflicts.csv.')
    print(f'Результаты сохранены: {OUTPUT_DIR}')

    from plot_flight_counts import build_charts

    for image in build_charts(OUTPUT_DIR):
        print(f'Диаграмма: {image}')
