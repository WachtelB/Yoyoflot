"""Распределение пассажиров по числу билетов с признаком багажа."""

import csv
import json
from collections import Counter
from pathlib import Path

import numpy as np
from passenger_metrics_common import run_metrics

SHOW_WINDOW = __import__('os').environ.get('SPY_NO_WINDOW') != '1'

SCRIPT_DIR = Path(__file__).resolve().parent
DATABASE = SCRIPT_DIR.parents[1] / 'databaze' / 'yoyoflot.duckdb'
SQL_FILE = SCRIPT_DIR / 'passenger_baggage_counts.sql'
OUTPUT_DIR = SCRIPT_DIR / 'results' / 'passenger_baggage_counts'


def count_baggage_flights(connection):
    """Документ, число уникальных билетов с багажом и ФИО."""
    return connection.execute(SQL_FILE.read_text(encoding='utf-8')).fetchall()


def calculate_quartiles(counts):
    """Каждый документ — одно наблюдение, включая пассажиров со счётчиком 0."""
    if not counts:
        return None
    q1, q3 = np.quantile([count for document, count, name in counts],
                         [0.25, 0.75], method='linear')
    return {'passenger_count': len(counts), 'q1': float(q1), 'q3': float(q3)}


def save_csv(path, headers, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.writer(file, delimiter=';')
        writer.writerow(headers)
        writer.writerows(rows)


def plot_baggage_histogram(distribution, stats, path):
    """X — число перелётов с багажом, Y — число пассажиров."""
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    figure, axis = plt.subplots(figsize=(12, 7))
    figure.canvas.manager.set_window_title('Перелёты с багажом — Q1 и Q3')
    flights = [count for count, passengers in distribution]
    passengers = [passengers for count, passengers in distribution]
    if flights:
        bars = axis.bar(flights, passengers, color='#287F8E', width=0.85)
        axis.bar_label(bars, padding=3, fontsize=9)
        if max(flights) <= 40:
            axis.set_xticks(range(max(flights) + 1))
        axis.margins(y=0.15)
    else:
        axis.text(0.5, 0.5, 'Нет данных', transform=axis.transAxes, ha='center')
    if stats is not None:
        axis.axvline(stats['q1'], color='#D97706', linestyle='--', linewidth=2,
                     label=f"Q1 = {stats['q1']:g}")
        axis.axvline(stats['q3'], color='#7C3AED', linestyle=':', linewidth=2,
                     label=f"Q3 = {stats['q3']:g}")
        axis.legend(title='По всем пассажирам, включая 0')
    axis.set_title('Распределение пассажиров по числу перелётов с признаком багажа')
    axis.set_xlabel('Число перелётов с признаком багажа (уникальных билетов)')
    axis.set_ylabel('Число пассажиров (документов)')
    axis.xaxis.set_major_locator(MaxNLocator(integer=True))
    axis.yaxis.set_major_locator(MaxNLocator(integer=True))
    axis.set_axisbelow(True)
    axis.grid(axis='y', alpha=0.2)
    figure.text(0.5, 0.035,
                '0 — нет известных билетов с выбранным признаком багажа.\n'
                'Sirena: 1PC и 2PC обозначают багажную норму, а не факт сдачи багажа.',
                ha='center', fontsize=9)
    figure.tight_layout(rect=(0, 0.10, 1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160)
    return figure


def save_report(counts):
    """Сохранить расчёт и создать график; окно открывает общий запуск."""
    distribution = sorted(Counter(count for document, count, name in counts).items())
    stats = calculate_quartiles(counts)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_csv(OUTPUT_DIR / 'passengers.csv', ['document', 'baggage_flight_count', 'full_name'], counts)
    save_csv(OUTPUT_DIR / 'distribution.csv', ['baggage_flight_count', 'passenger_count'], distribution)
    (OUTPUT_DIR / 'statistics.json').write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    figure = plot_baggage_histogram(distribution, stats, OUTPUT_DIR / 'histogram.png')
    if stats is not None:
        print(f"Пассажиров: {stats['passenger_count']}; Q1 = {stats['q1']:g}; Q3 = {stats['q3']:g}")
    print(f'Результаты сохранены: {OUTPUT_DIR}')
    return figure


if __name__ == '__main__':
    run_metrics([], SHOW_WINDOW, additional_reports=[(count_baggage_flights, save_report)])

