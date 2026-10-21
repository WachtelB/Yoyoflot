"""Число уникальных билетов каждого документа и распределение пассажиров."""

import csv
import json
from collections import Counter
from pathlib import Path
from statistics import NormalDist

import numpy as np
from passenger_metrics_common import run_metrics

SHOW_WINDOW = __import__('os').environ.get('SPY_NO_WINDOW') != '1'

SELECTED_FLIGHT_COUNT = 15

ALPHA = 0.05

SCRIPT_DIR = Path(__file__).resolve().parent
DATABASE = SCRIPT_DIR.parents[1] / 'databaze' / 'yoyoflot.duckdb'
SQL_FILE = SCRIPT_DIR / 'passenger_flight_counts.sql'
OUTPUT_DIR = SCRIPT_DIR / 'results' / 'passenger_flight_counts'


def count_passenger_flights(connection):
    """Возвращает номер документа, число уникальных билетов и ФИО."""
    return connection.execute(SQL_FILE.read_text(encoding='utf-8')).fetchall()


def get_passenger_names(counts, flight_count):
    """ФИО только для выбранного числа перелётов. Неизвестные имена пропускаем."""
    return [name for document, count, name in counts if count == flight_count and name]


def save_csv(path, headers, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.writer(file, delimiter=';')
        writer.writerow(headers)
        writer.writerows(rows)


def calculate_statistics(distribution, alpha=ALPHA):
    """Квартили и приближённый ДИ среднего по всем пассажирам, с учётом частот."""
    if not 0 < alpha < 1:
        raise ValueError('ALPHA должна быть между 0 и 1, например 0.05.')
    if not distribution:
        return None

    values = np.repeat(
        [flight_count for flight_count, passenger_count in distribution],
        [passenger_count for flight_count, passenger_count in distribution],
    )
    if len(values) == 0:
        return None
    q1, q3 = np.quantile(values, [0.25, 0.75])
    mean = float(np.mean(values))
    result = {
        'passenger_count': len(values),
        'q1': float(q1),
        'q3': float(q3),
        'mean': mean,
        'alpha': alpha,
        'confidence_level': 1 - alpha,
        'standard_error': None,
        'ci_lower': None,
        'ci_upper': None,
        'ci_method': 'normal approximation: mean +/- z * sample_std / sqrt(n)',
    }
    if len(values) >= 2:
        standard_error = float(np.std(values, ddof=1) / np.sqrt(len(values)))
        z = NormalDist().inv_cdf(1 - alpha / 2)
        result['standard_error'] = standard_error
        result['ci_lower'] = mean - z * standard_error
        result['ci_upper'] = mean + z * standard_error
    return result


def save_histogram(distribution, path, stats=None):
    """X — число перелётов, Y — число документов с таким числом перелётов."""
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FormatStrFormatter, MaxNLocator

    flights = [flight_count for flight_count, passenger_count in distribution]
    passengers = [passenger_count for flight_count, passenger_count in distribution]

    fig, axis = plt.subplots(figsize=(12, 7))
    fig.canvas.manager.set_window_title('Перелёты пассажиров — Q1, Q3 и ДИ среднего')
    if flights:
        axis.bar(flights, passengers, width=0.85, color='#287F8E')
        axis.set_xlim(min(flights) - 0.7, max(flights) + 0.7)
    else:
        axis.text(0.5, 0.5, 'Нет данных', ha='center', va='center', transform=axis.transAxes)

    if stats is None:
        stats = calculate_statistics(distribution)
    if stats is not None:
        axis.axvline(stats['q1'], color='#D97706', linestyle='--', linewidth=2,
                     label=f"Q1 (25%) = {stats['q1']:g}")
        axis.axvline(stats['q3'], color='#7C3AED', linestyle='--', linewidth=2,
                     label=f"Q3 (75%) = {stats['q3']:g}")
        axis.axvline(stats['mean'], color='#B91C1C', linewidth=1.5,
                     label=f"Среднее = {stats['mean']:.4f}")

        if stats['ci_lower'] is not None:
            lower, upper = stats['ci_lower'], stats['ci_upper']
            level = f"{stats['confidence_level']:.0%}"
            axis.axvspan(lower, upper, color='#E76F51', alpha=0.35,
                         label=f'{level} ДИ среднего: [{lower:.4f}; {upper:.4f}]')

            inset = axis.inset_axes([0.59, 0.50, 0.36, 0.19])
            inset.errorbar(stats['mean'], 0,
                           xerr=[[stats['mean'] - lower], [upper - stats['mean']]],
                           fmt='o', color='#B91C1C', capsize=7, linewidth=2)
            padding = max((upper - lower) * 0.3, 0.001)
            inset.set_xlim(lower - padding, upper + padding)
            inset.set_ylim(-1, 1)
            inset.set_yticks([])
            inset.xaxis.set_major_locator(MaxNLocator(3))
            inset.xaxis.set_major_formatter(FormatStrFormatter('%.3f'))
            inset.set_title(f'{level} ДИ среднего · увеличенный масштаб', fontsize=10)
            inset.set_xlabel('Нормальное приближение', fontsize=9)
            inset.grid(axis='x', alpha=0.2)
        axis.legend(loc='upper right', fontsize=10)

    axis.set_title('Распределение пассажиров по числу перелётов',
                   fontsize=16, fontweight='bold', pad=18)
    axis.set_xlabel('Число перелётов (уникальных билетов)', fontsize=12)
    axis.set_ylabel('Число пассажиров (документов)', fontsize=12)
    axis.xaxis.set_major_locator(MaxNLocator(integer=True))
    if flights and max(flights) <= 40:
        axis.set_xticks(range(min(flights), max(flights) + 1))
    axis.yaxis.set_major_locator(MaxNLocator(integer=True))
    axis.set_axisbelow(True)
    axis.grid(axis='y', color='#E2E8F0')
    for side in ['top', 'right']:
        axis.spines[side].set_visible(False)
    fig.text(0.5, 0.025,
             '0 — у документа нет известного номера билета; это не означает отсутствие реальных перелётов.',
             ha='center', fontsize=9, color='#475569')
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(path, dpi=180, facecolor='white')
    return fig


def save_report(counts):
    """Сохранить расчёт и создать график; окно открывает общий запуск."""
    distribution = sorted(Counter(count for document, count, name in counts).items())

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    passengers_file = OUTPUT_DIR / 'passengers.csv'
    distribution_file = OUTPUT_DIR / 'distribution.csv'
    histogram_file = OUTPUT_DIR / 'histogram.png'
    statistics_file = OUTPUT_DIR / 'statistics.json'

    save_csv(passengers_file, ['document', 'flight_count', 'full_name'], counts)
    save_csv(distribution_file, ['flight_count', 'passenger_count'], distribution)
    stats = calculate_statistics(distribution)
    statistics_file.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')
    figure = save_histogram(distribution, histogram_file, stats)

    for name in get_passenger_names(counts, SELECTED_FLIGHT_COUNT):
        print(name)

    print(f'Число перелётов пассажиров: {OUTPUT_DIR}')
    return figure


if __name__ == '__main__':
    run_metrics([], SHOW_WINDOW, additional_reports=[(count_passenger_flights, save_report)])

