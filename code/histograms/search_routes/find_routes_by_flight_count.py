"""Поиск маршрутов по значению X на гистограмме числа рейсов."""

import json
from pathlib import Path

import duckdb


ROUTE_TYPE = 'airport'

SELECTED_X = 2


DIRECTORY = Path(__file__).resolve().parent
PROJECT = DIRECTORY.parents[2]
DATABASE = PROJECT / 'databaze' / 'yoyoflot.duckdb'
SQL_FILE = DIRECTORY.parent / 'flight_route_counts.sql'
OUTPUT_FILE = DIRECTORY.parent / 'results' / 'route_search' / 'find_routes_by_flight_count.txt'


SOURCES = {
    'city': [
        ('boarding_passes', 'from_city', 'to_city'),
        ('forum_flights', 'from_city', 'to_city'),
    ],
    'airport': [
        ('boarding_passes', 'from_iata', 'to_iata'),
        ('sirena', 'From', 'Dest'),
        ('forum_flights', 'from_iata', 'to_iata'),
        ('pointz_activities', 'origin', 'destination'),
        ('skyteam_exchange', 'from_iata', 'to_iata'),
    ],
}


def selected_counts(value):
    """Приводит SELECTED_X к множеству целых значений."""
    values = value if isinstance(value, (list, tuple, set)) else [value]
    if not values or any(not isinstance(item, int) or item < 1 for item in values):
        raise ValueError('SELECTED_X должен быть целым числом от 1 или списком таких чисел')
    return set(values)


def find_routes(connection, route_type, wanted_counts):
    """Возвращает пары, у которых число уникальных рейсов равно SELECTED_X."""
    if route_type not in SOURCES:
        raise ValueError("ROUTE_TYPE должен быть 'city' или 'airport'")

    rows = connection.execute(SQL_FILE.read_text(encoding='utf-8')).fetchall()
    return sorted(
        [row for row in rows if row[0] == route_type and row[3] in wanted_counts],
        key=lambda row: (row[3], row[1], row[2]),
    )


def source_rows(connection, route_type, origin, destination):
    """Читает полные исходные строки всех таблиц для одной пары."""
    result = []
    for table, from_column, to_column in SOURCES[route_type]:
        query = f'''
            SELECT *
            FROM source."{table}"
            WHERE UPPER(TRIM("{from_column}")) = UPPER(TRIM(?))
              AND UPPER(TRIM("{to_column}")) = UPPER(TRIM(?))
        '''
        cursor = connection.execute(query, [origin, destination])
        columns = [column[0] for column in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        result.append((table, rows))
    return result


def write_report(connection, routes, route_type, wanted_counts):
    """Записывает найденные пары и все исходные поля в TXT."""
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open('w', encoding='utf-8') as output:
        output.write('ПОИСК МАРШРУТОВ ПО ЧИСЛУ УНИКАЛЬНЫХ РЕЙСОВ\n')
        output.write(f'Тип маршрута: {route_type}\n')
        output.write(f'Выбранные значения X: {sorted(wanted_counts)}\n')
        output.write(f'Найдено пар: {len(routes)}\n')

        for _, origin, destination, flight_count in routes:
            output.write(f'\n{"=" * 80}\n')
            output.write(f'{origin} → {destination}: {flight_count} рейсов\n')
            for table, rows in source_rows(connection, route_type, origin, destination):
                output.write(f'\nТаблица source.{table}: {len(rows)} строк\n')
                for row in rows:
                    output.write(json.dumps(row, ensure_ascii=False, default=str) + '\n')


def main():
    wanted_counts = selected_counts(SELECTED_X)
    try:
        connection = duckdb.connect(str(DATABASE), read_only=True)
    except duckdb.IOException as error:
        raise SystemExit(
            f'Не удалось открыть базу: {error}\n'
            'Закрой приложение, которое использует файл базы, и повтори запуск.'
        )

    with connection:
        routes = find_routes(connection, ROUTE_TYPE, wanted_counts)
        write_report(connection, routes, ROUTE_TYPE, wanted_counts)

    print(f'Найдено пар: {len(routes)}')
    print(f'Результат сохранён: {OUTPUT_FILE}')


if __name__ == '__main__':
    main()
