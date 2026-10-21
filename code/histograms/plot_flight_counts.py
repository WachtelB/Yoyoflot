"""Столбчатые диаграммы по четырём CSV-отчётам о рейсах."""

import csv
from pathlib import Path

import matplotlib

matplotlib.use('Agg')  # Сохраняем картинки без открытия отдельных окон.
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator


RESULTS_DIR = Path(__file__).parent / 'results' / 'flights_by_location'
ROWS_PER_CHART = 25

REPORTS = [
    ('city_departures', 'Вылеты из городов', '#247A73'),
    ('city_arrivals', 'Прилёты в города', '#3A9188'),
    ('airport_departures', 'Вылеты из аэропортов', '#376DAD'),
    ('airport_arrivals', 'Прилёты в аэропорты', '#668ABD'),
]


def draw_bars(axis, rows, title, color):
    """Один столбец — один город или аэропорт; длина — число рейсов."""
    axis.set_title(title, loc='left', fontsize=13, fontweight='bold', pad=14)
    if not rows:
        axis.text(0.5, 0.5, 'Нет данных', ha='center', va='center', transform=axis.transAxes)
        axis.set_axis_off()
        return

    places = [place for place, count in rows]
    values = [count for place, count in rows]
    bars = axis.barh(places, values, color=color, height=0.65)
    axis.invert_yaxis()  # Самые редкие места сверху.
    axis.bar_label(bars, padding=5, fontsize=10)
    axis.set_xlim(0, max(values) * 1.18)
    axis.set_xlabel('Количество уникальных рейсов', fontsize=10, labelpad=8)
    axis.xaxis.set_major_locator(MaxNLocator(integer=True))
    axis.set_axisbelow(True)
    axis.grid(axis='x', color='#E2E8F0', linewidth=0.8)
    axis.tick_params(axis='both', length=0, labelsize=10)
    for side in ['top', 'right', 'left']:
        axis.spines[side].set_visible(False)
    axis.spines['bottom'].set_color('#CBD5E1')


def build_charts(results_dir=RESULTS_DIR):
    """Читает готовые CSV, сохраняет PNG и возвращает пути к ним."""
    charts_dir = results_dir / 'charts'
    charts_dir.mkdir(parents=True, exist_ok=True)
    reports = []
    images = []

    for filename, title, color in REPORTS:
        with (results_dir / f'{filename}.csv').open(encoding='utf-8-sig', newline='') as file:
            rows = [(row['location'], int(row['flight_count']))
                    for row in csv.DictReader(file, delimiter=';')]
        rows.sort(key=lambda row: (row[1], row[0]))
        reports.append((title, color, rows))

        pages = [rows[start:start + ROWS_PER_CHART]
                 for start in range(0, len(rows), ROWS_PER_CHART)] or [[]]
        for page_number, page in enumerate(pages, start=1):
            fig, axis = plt.subplots(figsize=(11, max(4, len(page) * 0.35 + 2)))
            page_title = title if len(pages) == 1 else f'{title} — {page_number}/{len(pages)}'
            draw_bars(axis, page, page_title, color)
            fig.tight_layout(pad=2)
            image = charts_dir / f'{filename}_{page_number:02d}.png'
            fig.savefig(image, dpi=170, facecolor='white', bbox_inches='tight')
            plt.close(fig)
            images.append(image)

    max_rows = max(len(rows) for title, color, rows in reports)
    if max_rows <= ROWS_PER_CHART:
        fig, axes = plt.subplots(2, 2, figsize=(15, max(9, max_rows * 0.65 + 4)))
        for axis, (title, color, rows) in zip(axes.flat, reports):
            draw_bars(axis, rows, title, color)
        fig.suptitle('Количество рейсов по направлениям', fontsize=20, fontweight='bold', y=0.98)
        fig.text(0.5, 0.925, 'Места из текущих отчётов · один рейс = номер + дата',
                 ha='center', fontsize=11, color='#475569')
        fig.tight_layout(rect=(0, 0, 1, 0.89), pad=2.5, h_pad=3)
        image = charts_dir / 'overview.png'
        fig.savefig(image, dpi=170, facecolor='white', bbox_inches='tight')
        plt.close(fig)
        images.append(image)

    (charts_dir / 'current_charts.txt').write_text(
        '\n'.join(image.name for image in images) + '\n', encoding='utf-8'
    )
    return images


if __name__ == '__main__':
    for image in build_charts():
        print(image)
