"""Число перелётов каждого номера рейса с учётом нескольких вылетов за день."""

import csv
from pathlib import Path

import duckdb
import matplotlib
import numpy as np

SHOW_WINDOW = __import__('os').environ.get('SPY_NO_WINDOW') != '1'
FLIGHTS_PER_PAGE = 20

matplotlib.use('TkAgg' if SHOW_WINDOW else 'Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
from matplotlib.widgets import Slider

SCRIPT_DIR = Path(__file__).resolve().parent
DATABASE = SCRIPT_DIR.parents[1] / 'databaze' / 'yoyoflot.duckdb'
SQL_FILE = SCRIPT_DIR / 'flight_number_counts.sql'
OUTPUT_DIR = SCRIPT_DIR / 'results' / 'flights_by_number'
HEADERS = ['flight_number', 'total_flights', 'boarding_data', 'boarding_passes',
           'sirena', 'forum_flights', 'pointz_activities', 'skyteam_exchange']


def count_flights_by_number(connection):
    """Общий счётчик и отдельные счётчики каждой исходной таблицы."""
    return connection.execute(SQL_FILE.read_text(encoding='utf-8')).fetchall()


def calculate_quartiles(counts):
    """Q1 и Q2 общего числа перелётов; каждый номер рейса имеет равный вес."""
    if not counts:
        return None
    q1, q2 = np.quantile([row[1] for row in counts], [0.25, 0.50], method='linear')
    return float(q1), float(q2)


def save_results(counts):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with (OUTPUT_DIR / 'counts.csv').open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.writer(file, delimiter=';')
        writer.writerow(HEADERS)
        writer.writerows(counts)
    with (OUTPUT_DIR / 'counts.txt').open('w', encoding='utf-8') as file:
        print('Число перелётов по номерам рейсов. Итог учитывает повторы между источниками.', file=file)
        quartiles = calculate_quartiles(counts)
        if quartiles is not None:
            q1, q2 = quartiles
            print(f'По всем номерам рейсов: Q1 = {q1:g}; Q2 (медиана) = {q2:g}', file=file)
        print('Поля: ' + ' | '.join(HEADERS), file=file)
        for row in counts:
            print(' | '.join(map(str, row)), file=file)


def plot_flight_counts(counts, path):
    """По X — номер рейса, по Y — объединённое число перелётов."""
    if FLIGHTS_PER_PAGE < 1:
        raise ValueError('FLIGHTS_PER_PAGE должна быть больше нуля')
    figure, axis = plt.subplots(figsize=(14, 7))
    figure.subplots_adjust(bottom=0.28, top=0.90)
    figure.canvas.manager.set_window_title('Число перелётов по номерам рейсов')
    pages = max(1, (len(counts) + FLIGHTS_PER_PAGE - 1) // FLIGHTS_PER_PAGE)
    quartiles = calculate_quartiles(counts)

    def draw_page(page):
        page = int(page)
        start = (page - 1) * FLIGHTS_PER_PAGE
        rows = counts[start:start + FLIGHTS_PER_PAGE]
        axis.clear()
        bars = axis.bar(range(len(rows)), [row[1] for row in rows], color='#2563EB')
        axis.set_xticks(range(len(rows)), [row[0] for row in rows], rotation=60, ha='right')
        axis.bar_label(bars, padding=3, fontsize=8)
        if quartiles is not None:
            q1, q2 = quartiles
            axis.axhline(q1, color='#D97706', linestyle='--', label=f'Q1 = {q1:g}')
            axis.axhline(q2, color='#9333EA', linestyle=':', label=f'Q2 (медиана) = {q2:g}')
            axis.legend(loc='upper right', title='По всем номерам рейсов')
        axis.set_xlabel('Номер рейса')
        axis.set_ylabel('Число перелётов')
        axis.set_title(f'Число перелётов — страница {page}/{pages}, номеров рейсов: {len(counts)}')
        axis.yaxis.set_major_locator(MaxNLocator(integer=True))
        axis.set_axisbelow(True)
        axis.grid(axis='y', alpha=0.2)
        axis.margins(y=0.15)
        if not rows:
            axis.text(0.5, 0.5, 'Нет данных', transform=axis.transAxes, ha='center')
        figure.canvas.draw_idle()

    draw_page(1)
    if pages > 1:
        slider = Slider(figure.add_axes([0.20, 0.05, 0.65, 0.03]), 'Страница',
                        1, pages, valinit=1, valstep=1, valfmt='%d')
        slider.on_changed(draw_page)
        figure.page_slider = slider  # Сохраняем ссылку для работы ползунка.
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160)
    return figure


if __name__ == '__main__':
    try:
        connection = duckdb.connect(str(DATABASE), read_only=True)
    except duckdb.IOException as error:
        raise SystemExit(
            f'Не удалось открыть базу: {error}\n'
            'Закрой приложение, которое использует файл базы, и повтори запуск.'
        )
    with connection:
        counts = count_flights_by_number(connection)

    save_results(counts)
    figure = plot_flight_counts(counts, OUTPUT_DIR / 'histogram.png')
    print(f'Результаты сохранены: {OUTPUT_DIR}')
    if SHOW_WINDOW:
        plt.show()
    plt.close(figure)

