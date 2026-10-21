"""Число уникальных рейсов для каждой пары городов и аэропортов."""

import json
from contextlib import redirect_stdout
from pathlib import Path

import duckdb
import matplotlib
import numpy as np

SHOW_WINDOW = __import__('os').environ.get('SPY_NO_WINDOW') != '1'
PAIRS_PER_PAGE = 12  # Сколько пар одновременно показывать на каждом графике.

matplotlib.use('TkAgg' if SHOW_WINDOW else 'Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
from matplotlib.widgets import Slider


DATABASE = Path(__file__).resolve().parents[2] / 'databaze' / 'yoyoflot.duckdb'
SQL_FILE = Path(__file__).with_name('flight_route_counts.sql')
OUTPUT_FILE = Path(__file__).resolve().parent / 'results' / 'flight_routes.txt'
HISTOGRAM_FILE = OUTPUT_FILE.with_name('flight_routes_histogram.png')
RARE_ROUTES_FILE = OUTPUT_FILE.with_name('rare_route_rows.txt')

ROUTE_TYPE = 'city'
SELECTED_PAIR = ('MINNEAPOLIS/ST PAUL MN', 'SHANGHAI')  # Отправление, прибытие. None — не выводить строки.
FLIGHT_THRESHOLD = 10  # Выгружать пары, у которых число рейсов строго меньше порога.


def count_flight_routes(connection):
    """Возвращает тип пары, отправление, назначение и число рейсов."""
    sql = SQL_FILE.read_text(encoding='utf-8')
    return connection.execute(sql).fetchall()


def calculate_route_quartiles(counts, route_type):
    """Q1 и Q3 по всем парам категории: каждая пара имеет одинаковый вес."""
    values = [count for kind, origin, destination, count in counts if kind == route_type]
    if not values:
        return None
    q1, q3 = np.quantile(values, [0.25, 0.75], method='linear')
    return float(q1), float(q3)


def plot_route_histograms(counts, path=HISTOGRAM_FILE):
    """По X — названия пар, по Y — число рейсов; все пары доступны по страницам."""
    if PAIRS_PER_PAGE < 1:
        raise ValueError('PAIRS_PER_PAGE должна быть больше нуля')
    figure = plt.figure(figsize=(16, 11))
    figure.canvas.manager.set_window_title('Рейсы между городами и аэропортами')
    sliders = []

    def add_chart(kind, title, color, chart_position, slider_position):
        rows = sorted([row for row in counts if row[0] == kind],
                      key=lambda row: (-row[3], row[1], row[2]))
        pages = max(1, (len(rows) + PAIRS_PER_PAGE - 1) // PAIRS_PER_PAGE)
        axis = figure.add_axes(chart_position)
        quartiles = calculate_route_quartiles(counts, kind)

        def draw_page(page):
            page = int(page)
            start = (page - 1) * PAIRS_PER_PAGE
            selected = rows[start:start + PAIRS_PER_PAGE]
            axis.clear()
            labels = [f'{origin} → {destination}' for _, origin, destination, _ in selected]
            values = [count for _, _, _, count in selected]
            bars = axis.bar(range(len(selected)), values, color=color)
            axis.set_xticks(range(len(selected)), labels, rotation=45, ha='right', fontsize=8)
            axis.bar_label(bars, padding=3, fontsize=8)
            if quartiles is not None:
                q1, q3 = quartiles
                axis.axhline(q1, color='#D97706', linestyle='--', label=f'Q1 = {q1:g}')
                axis.axhline(q3, color='#9333EA', linestyle=':', label=f'Q3 = {q3:g}')
                axis.legend(loc='upper right', title='По всем парам', fontsize=9)
            axis.margins(y=0.15)
            if not selected:
                axis.text(0.5, 0.5, 'Нет данных', transform=axis.transAxes, ha='center')
            axis.set_title(f'{title} — страница {page}/{pages}, всего пар: {len(rows)}')
            axis.set_ylabel('Число уникальных рейсов')
            axis.yaxis.set_major_locator(MaxNLocator(integer=True))
            axis.set_axisbelow(True)
            axis.grid(axis='y', alpha=0.2)
            figure.canvas.draw_idle()

        draw_page(1)
        if pages > 1:
            slider = Slider(figure.add_axes(slider_position), 'Страница', 1, pages,
                            valinit=1, valstep=1, valfmt='%d')
            slider.on_changed(draw_page)
            sliders.append(slider)

    add_chart('city', 'Город → Город', '#2563EB',
              [0.08, 0.70, 0.88, 0.25], [0.20, 0.51, 0.65, 0.02])
    add_chart('airport', 'Аэропорт → Аэропорт', '#0D9488',
              [0.08, 0.22, 0.88, 0.25], [0.20, 0.04, 0.65, 0.02])
    figure.route_sliders = sliders
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160)
    return figure


def show_route_rows(connection, route_type, pair):
    """Показывает все исходные строки выбранной пары, включая повторы."""
    if pair is None:
        return

    sources = {
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
    if route_type not in sources:
        raise ValueError("ROUTE_TYPE должен быть 'city' или 'airport'")

    origin, destination = pair
    print(f'\nИсходные строки ({route_type}): {origin} → {destination}')
    for table, from_column, to_column in sources[route_type]:
        result = connection.execute(f'''
            SELECT *
            FROM source."{table}"
            WHERE UPPER(TRIM("{from_column}")) = UPPER(TRIM(?))
              AND UPPER(TRIM("{to_column}")) = UPPER(TRIM(?))
        ''', [origin, destination])
        columns = [column[0] for column in result.description]
        rows = result.fetchall()
        print(f'\nsource.{table} — строк: {len(rows)}')
        for number, row in enumerate(rows, start=1):
            print(f'Строка {number}:')
            print(json.dumps(dict(zip(columns, row)), ensure_ascii=False,
                             indent=2, default=str))


def save_routes_below_threshold(connection, counts, route_type, threshold,
                                path=RARE_ROUTES_FILE):
    """Сохраняет show_route_rows для всех пар с числом рейсов < threshold."""
    if route_type not in ('city', 'airport'):
        raise ValueError("ROUTE_TYPE должен быть 'city' или 'airport'")
    if threshold < 0:
        raise ValueError('Порог не должен быть отрицательным')

    routes = sorted(
        [row for row in counts if row[0] == route_type and row[3] < threshold],
        key=lambda row: (row[3], row[1], row[2]),
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as output, redirect_stdout(output):
        print(f'Тип пар: {route_type}. Число уникальных рейсов < {threshold}.')
        print(f'Подходящих пар: {len(routes)}')
        for _, origin, destination, flight_count in routes:
            print(f'\n{"=" * 70}\n{origin} → {destination}: {flight_count} рейсов')
            show_route_rows(connection, route_type, (origin, destination))
    return len(routes)


if __name__ == '__main__':
    try:
        connection = duckdb.connect(str(DATABASE), read_only=True)
    except duckdb.IOException as error:
        raise SystemExit(
            f'Не удалось открыть базу: {error}\n'
            'Закрой приложение, которое использует файл базы, и повтори запуск.'
        )

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with connection, OUTPUT_FILE.open('w', encoding='utf-8') as output, redirect_stdout(output):
        counts = count_flight_routes(connection)

        for route_type, title in [('city', 'Город → Город'), ('airport', 'Аэропорт → Аэропорт')]:
            routes = [row for row in counts if row[0] == route_type]
            print(f'\n{title} — всего пар: {len(routes)}')
            quartiles = calculate_route_quartiles(counts, route_type)
            if quartiles is not None:
                q1, q3 = quartiles
                print(f'Квартили числа рейсов по всем парам: Q1 = {q1:g}, Q3 = {q3:g}')
            for _, origin, destination, flight_count in routes:
                print(f'{origin} → {destination}: {flight_count}')

        show_route_rows(connection, ROUTE_TYPE, SELECTED_PAIR)
        rare_pair_count = save_routes_below_threshold(
            connection, counts, ROUTE_TYPE, FLIGHT_THRESHOLD
        )

    print(f'Отчёт сохранён: {OUTPUT_FILE}')
    print(f'Строки редких пар ({rare_pair_count}): {RARE_ROUTES_FILE}')

    figure = plot_route_histograms(counts)
    print(f'Гистограммы сохранены: {HISTOGRAM_FILE}')
    if SHOW_WINDOW:
        plt.show()
    plt.close(figure)

