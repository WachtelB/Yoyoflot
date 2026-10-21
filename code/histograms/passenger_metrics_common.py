"""Общие связи по документам, сохранение результатов и гистограммы."""

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import textwrap

import duckdb
import numpy as np

DIRECTORY = Path(__file__).resolve().parent
DATABASE = DIRECTORY.parents[1] / 'databaze' / 'yoyoflot.duckdb'
RESULTS = DIRECTORY / 'results' / 'passenger_metrics'


@dataclass(frozen=True)
class Flight:
    number: str
    date: object
    time: object
    origin: str | None
    destination: str | None

    @property
    def departure(self):
        return datetime.combine(self.date, self.time) if self.time is not None else None

    @property
    def route(self):
        return (self.origin, self.destination) if self.origin and self.destination else None


@dataclass
class PassengerData:
    passengers: dict
    flights: dict
    cards: dict = field(default_factory=dict)
    audit: dict = field(default_factory=dict)
    card_evidence: list = field(default_factory=list)


@dataclass
class Metric:
    name: str
    title: str
    label: str
    values: dict
    note: str
    integer: bool = True
    details: list = field(default_factory=list)


def load_data(connection, include_cards=False):
    """Временные таблицы, только однозначная связь посадочных талонов по билету."""
    connection.execute((DIRECTORY / 'prepare_passenger_metrics.sql').read_text(encoding='utf-8'))
    passengers = dict(connection.execute('SELECT document, full_name FROM passengers ORDER BY document').fetchall())
    flights = defaultdict(list)
    for document, number, date, time, origin, destination in connection.execute('''
        SELECT * FROM passenger_events
        ORDER BY document, flight_date, flight_time NULLS LAST, flight_number
    ''').fetchall():
        flights[document].append(Flight(number, date, time, origin, destination))

    def number(sql):
        return connection.execute(sql).fetchone()[0]

    audit = {
        'passengers': len(passengers),
        'events': sum(map(len, flights.values())),
        'ambiguous_tickets_excluded_from_boarding_passes': number(
            'SELECT COUNT(*) FROM ticket_owners WHERE owner_count > 1'),
        'boarding_pass_rows_not_linked_to_one_document': number('''
            SELECT COUNT(*) FROM source.boarding_passes bp LEFT JOIN ticket_owners o
            ON norm_id(bp.e_ticket) = o.ticket WHERE o.owner_count IS NULL OR o.owner_count <> 1
        '''),
        'raw_rows_without_flight_number_or_date': number('''
            SELECT COUNT(*) FROM passenger_raw_flights WHERE flight_number IS NULL OR flight_date IS NULL
        '''),
        'conflicting_route_days_excluded_from_route_metrics': number(
            'SELECT COUNT(*) FROM passenger_day_routes WHERE route_count > 1'),
        'events_without_time': number('SELECT COUNT(*) FROM passenger_events WHERE flight_time IS NULL'),
        'events_without_unambiguous_route': number('SELECT COUNT(*) FROM passenger_events WHERE origin IS NULL'),
        'multiple_departure_times_for_same_document_flight_date': number('''
            SELECT COUNT(*) FROM (SELECT document, flight_number, flight_date FROM passenger_events
            GROUP BY ALL HAVING COUNT(*) > 1)
        '''),
        'time_basis': 'Local source timestamps; no timezone conversion. Conflicting times count separately.',
    }
    cards = defaultdict(set)
    evidence = []
    if include_cards:
        connection.execute((DIRECTORY / 'prepare_loyalty_metrics.sql').read_text(encoding='utf-8'))
        for document, card, basis in connection.execute(
            'SELECT * FROM passenger_cards ORDER BY document, card, basis'
        ).fetchall():
            cards[document].add(card)
            evidence.append({'document': document, 'card': card, 'basis': basis})
        audit['direct_cards_shared_by_documents'] = number(
            'SELECT COUNT(*) FROM direct_card_owners WHERE owner_count > 1')
        audit['ambiguous_profiles_not_used'] = number(
            'SELECT COUNT(*) FROM profile_owners WHERE owner_count > 1 OR max_card_owners > 1')
        audit['profile_cards_not_parsed'] = number('SELECT COUNT(*) FROM profile_cards WHERE card IS NULL')
        audit['sirena_rows_with_ff_marker_but_unparsed_card'] = number('''
            SELECT COUNT(*) FROM source.sirena
            WHERE CONTAINS(UPPER(PaxAdditionalInfo), 'FF#')
              AND LEN(REGEXP_EXTRACT_ALL(UPPER(PaxAdditionalInfo), 'FF#[A-Z0-9]{2}\\s+[0-9]+\\b')) = 0
        ''')
    return PassengerData(passengers, dict(flights), dict(cards), audit, evidence)


def calculate_statistics(values):
    known = [value for value in values.values() if value is not None]
    q1, q3 = np.quantile(known, [0.25, 0.75], method='linear') if known else (None, None)
    return {'included_passengers': len(known), 'excluded_passengers': len(values) - len(known),
            'q1': float(q1) if q1 is not None else None,
            'q3': float(q3) if q3 is not None else None}


def save_dicts(path, rows, headers=None):
    with path.open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=headers or list(rows[0]), delimiter=';')
        writer.writeheader()
        writer.writerows(rows)


def save_metric(data, metric, plt):
    folder = RESULTS / metric.name
    folder.mkdir(parents=True, exist_ok=True)
    rows = []
    for document, name in data.passengers.items():
        flights = data.flights.get(document, [])
        rows.append({'document': document, 'full_name': name, 'value': metric.values[document],
                     'known_flights': len(flights),
                     'flights_with_time': sum(f.time is not None for f in flights),
                     'flights_with_route': sum(f.route is not None for f in flights)})
    save_dicts(folder / 'passengers.csv', rows,
               ['document', 'full_name', 'value', 'known_flights', 'flights_with_time', 'flights_with_route'])
    distribution = sorted(Counter(v for v in metric.values.values() if v is not None).items())
    save_dicts(folder / 'distribution.csv', [{'value': v, 'passengers': n} for v, n in distribution],
               ['value', 'passengers'])
    if metric.details:
        save_dicts(folder / 'details.csv', metric.details)
    elif (folder / 'details.csv').exists():
        old_headers = (folder / 'details.csv').read_text(encoding='utf-8-sig').splitlines()[0]
        (folder / 'details.csv').write_text(old_headers + '\n', encoding='utf-8-sig')
    stats = calculate_statistics(metric.values)
    stats.update({'metric': metric.name, 'definition': metric.note, 'quantile_method': 'linear'})
    (folder / 'statistics.json').write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')

    from matplotlib.ticker import MaxNLocator
    figure, axis = plt.subplots(figsize=(12, 7))
    figure.canvas.manager.set_window_title(metric.title)
    known = [v for v in metric.values.values() if v is not None]
    if known:
        if metric.integer and len(distribution) <= 60:
            axis.bar([v for v, n in distribution], [n for v, n in distribution], color='#287F8E')
        else:
            axis.hist(known, bins=min(40, max(1, len(set(known)))), color='#287F8E', edgecolor='white')
        axis.axvline(stats['q1'], color='#D97706', linestyle='--', linewidth=2, label=f"Q1 = {stats['q1']:g}")
        axis.axvline(stats['q3'], color='#7C3AED', linestyle=':', linewidth=2, label=f"Q3 = {stats['q3']:g}")
        axis.legend()
    else:
        axis.text(0.5, 0.5, 'Нет подходящих наблюдений', transform=axis.transAxes, ha='center')
    axis.set_title(f"{metric.title}\nУчтено документов: {stats['included_passengers']}; недостаточно данных: {stats['excluded_passengers']}")
    axis.set_xlabel(metric.label)
    axis.set_ylabel('Число пассажиров (документов)')
    if metric.integer:
        axis.xaxis.set_major_locator(MaxNLocator(integer=True))
        if known and max(known) - min(known) <= 25:
            axis.set_xticks(range(int(min(known)), int(max(known)) + 1))
            axis.set_xlim(min(known) - 0.8, max(known) + 0.8)
    axis.yaxis.set_major_locator(MaxNLocator(integer=True))
    axis.set_axisbelow(True)
    axis.grid(axis='y', alpha=0.2)
    figure.text(0.5, 0.025, textwrap.fill(metric.note, 115), ha='center', fontsize=8)
    figure.tight_layout(rect=(0, 0.13, 1, 1))
    figure.savefig(folder / 'histogram.png', dpi=160)
    print(f"{metric.title}: Q1={stats['q1']}, Q3={stats['q3']}. {folder}")
    return figure


def run_metrics(calculators, show_window=True, include_cards=False, additional_reports=()):
    try:
        connection = duckdb.connect(str(DATABASE), read_only=True)
    except duckdb.IOException as error:
        raise SystemExit(f'{error}\nЗакрой приложение, которое использует файл базы, и повтори запуск.')
    with connection:
        data = load_data(connection, include_cards) if calculators else None
        prepared_reports = [(save_report, read_counts(connection))
                            for read_counts, save_report in additional_reports]
    import matplotlib
    matplotlib.use('TkAgg' if show_window else 'Agg')
    import matplotlib.pyplot as plt
    RESULTS.mkdir(parents=True, exist_ok=True)
    audit_file = 'input_audit_with_cards.json' if include_cards else 'input_audit.json'
    if data is not None:
        (RESULTS / audit_file).write_text(json.dumps(data.audit, ensure_ascii=False, indent=2), encoding='utf-8')
    if include_cards and data is not None:
        save_dicts(RESULTS / 'card_links.csv', data.card_evidence, ['document', 'card', 'basis'])
    for calculate in calculators:
        for metric in calculate(data):
            figure = save_metric(data, metric, plt)
            if not show_window:
                plt.close(figure)
    for save_report, counts in prepared_reports:
        figure = save_report(counts)
        if not show_window:
            plt.close(figure)
    lines = ['# Метрики пассажиров', '',
             'Значения по документам. NULL исключён из квартилей; нули включены.', '',
             '| Метрика | С оценкой | Без оценки | Q1 | Q3 | График |',
             '| --- | ---: | ---: | ---: | ---: | --- |']
    for path in sorted(RESULTS.glob('*/statistics.json')):
        stats = json.loads(path.read_text(encoding='utf-8'))
        name = path.parent.name
        lines.append(f"| [{name}]({name}/passengers.csv) | {stats['included_passengers']} | "
                     f"{stats['excluded_passengers']} | {stats['q1']} | {stats['q3']} | "
                     f"[PNG]({name}/histogram.png) |")
    lines += ['', 'Каждый каталог содержит результаты последнего запуска соответствующего скрипта.',
              '', 'Гистограммы по уникальным билетам (прежние папки результатов):',
              '- [Число перелётов](../passenger_flight_counts/histogram.png)',
              '- [Число перелётов с признаком багажа](../passenger_baggage_counts/histogram.png)',
              '', '[Правила расчёта и команды запуска](../../README.md)', '']
    (RESULTS / 'README.md').write_text('\n'.join(lines), encoding='utf-8')
    if show_window:
        plt.show()
    plt.close('all')
