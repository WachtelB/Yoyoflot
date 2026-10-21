"""Поиск документов по X гистограммы и полная выгрузка исходных строк в TXT."""

import importlib
import json
import math
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parent
HISTOGRAMS = DIRECTORY.parent
sys.path.insert(0, str(HISTOGRAMS))

import duckdb
from passenger_metrics_common import DATABASE, Metric, load_data

OUTPUT_DIR = HISTOGRAMS / 'results' / 'user_search'
CALCULATORS = {
    'unique_routes': 'count_unique_routes',
    'max_flights_7_days': 'count_max_flights',
    'max_flights_30_days': 'count_max_flights',
    'min_flight_interval': 'count_min_flight_interval',
    'route_repetitions': 'count_route_repetitions',
    'quick_returns': 'count_quick_returns',
    'airlines': 'count_airlines',
    'loyalty_cards': 'count_loyalty_cards',
}
LEGACY_SQL = {
    'passenger_flights': ('passenger_flight_counts.sql', 'Число перелётов пассажира'),
    'passenger_baggage_flights': ('passenger_baggage_counts.sql', 'Число перелётов с признаком багажа'),
}


@dataclass
class Selection:
    metric: str
    x: object
    value_range: tuple | None = None  # Интервал [левая граница, правая граница).
    lower_exclusive: float | None = None  # Выбросы: X строго больше границы.


def select_documents(values, x, value_range=None, lower_exclusive=None):
    """Одно X, список X, интервал или значения строго выше границы."""
    if lower_exclusive is not None:
        if value_range is not None:
            raise ValueError('Нельзя одновременно задавать интервал и нижнюю границу выброса')
        if isinstance(lower_exclusive, bool) or not isinstance(lower_exclusive, (int, float)) \
                or not math.isfinite(lower_exclusive):
            raise ValueError('Граница выброса должна быть конечным числом')
        return ({doc for doc, value in values.items()
                 if value is not None and value > lower_exclusive},
                f'X > {lower_exclusive:g}')
    if value_range is not None:
        lower, upper = value_range
        if not all(math.isfinite(v) for v in (lower, upper)) or lower >= upper:
            raise ValueError('Интервал должен иметь конечные границы: левая < правая')
        return {doc for doc, value in values.items()
                if value is not None and lower <= value < upper}, f'{lower:g} <= X < {upper:g}'

    if x is None:
        known = [value for value in values.values() if value is not None]
        if not known:
            return set(), 'Нет известных значений X'
        x = min(known)
    targets = list(x) if isinstance(x, (list, tuple, set)) else [x]
    if not targets or any(isinstance(v, bool) or not isinstance(v, (int, float))
                          or not math.isfinite(v) for v in targets):
        raise ValueError('SELECTED_X: число, список чисел или None (минимум)')
    selected = {doc for doc, value in values.items() if value is not None
                and any(math.isclose(value, target, rel_tol=0, abs_tol=1e-9) for target in targets)}
    return selected, 'X = ' + ', '.join(f'{value:g}' for value in targets)


class SearchContext:
    def __init__(self, connection):
        self.connection = connection
        self.data = load_data(connection, include_cards=True)
        self.metrics = {}
        self.source_rows_ready = False

    def metric(self, name):
        if name not in self.metrics:
            if name in LEGACY_SQL:
                filename, title = LEGACY_SQL[name]
                rows = self.connection.execute((HISTOGRAMS / filename).read_text(encoding='utf-8')).fetchall()
                self.metrics[name] = Metric(name, title, 'Число билетов',
                    {document: count for document, count, full_name in rows},
                    ('Уникальные билеты каждого документа по BoardingData и Sirena; нули включены.'
                     if name == 'passenger_flights' else
                     'Уникальные билеты с Registered/Transit/Delayed в BoardingData или 1PC/2PC в Sirena. '
                     'Достаточно признака в одном источнике; нули включены. '
                     'В Sirena это багажная норма, а не подтверждение сдачи багажа.'))
            else:
                module = importlib.import_module(CALCULATORS[name])
                for metric in module.calculate(self.data):
                    self.metrics[metric.name] = metric
        if name not in self.metrics:
            raise ValueError(f'Метрика {name} не рассчитана. Проверь WINDOW_DAYS в count_max_flights.py.')
        return self.metrics[name]

    def source_rows(self, documents, metric_name):
        if not documents:
            return
        if not self.source_rows_ready:
            self.connection.execute((DIRECTORY / 'source_rows.sql').read_text(encoding='utf-8'))
            self.source_rows_ready = True
        self.connection.execute('''CREATE OR REPLACE TEMP TABLE search_documents AS
                                   SELECT UNNEST(FROM_JSON(?, '["VARCHAR"]')) AS document''',
                                [json.dumps(sorted(documents))])
        tables = ['boarding_data', 'sirena']
        if metric_name in CALCULATORS and metric_name != 'loyalty_cards':
            tables.append('boarding_passes')
        if metric_name == 'loyalty_cards':
            tables += ['forum_loyalty', 'pointz_activities']
        result = self.connection.execute('''
            SELECT r.document, r.source_table, r.row_json
            FROM search_source_rows r JOIN search_documents d USING (document)
            WHERE r.source_table IN (SELECT UNNEST(?::VARCHAR[]))
            ORDER BY r.document, r.source_table
        ''', [tables])
        while batch := result.fetchmany(1000):
            yield from batch


def save_finished_report(temporary, path):
    """Если Windows запрещает замену отчёта, сохраняем новый файл рядом."""
    try:
        temporary.replace(path)
        return path
    except PermissionError:
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        alternative = path.with_name(f'{path.stem}_{stamp}{path.suffix}')
        with temporary.open('rb') as source, alternative.open('xb') as target:
            shutil.copyfileobj(source, target)
        try:
            temporary.unlink()
        except PermissionError:
            pass
        print(f'Windows не разрешил заменить {path.name}. Новый отчёт: {alternative}', flush=True)
        return alternative


def write_report(context, filename, selections, output_dir=OUTPUT_DIR):
    """Один TXT на мини-скрипт. Внутри — все выбранные документы без ограничения."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    temporary = path.with_suffix('.txt.tmp')
    summary = []
    with temporary.open('w', encoding='utf-8') as file:
        print('ПОИСК ПАССАЖИРОВ ПО ЗНАЧЕНИЮ X ГИСТОГРАММЫ', file=file)
        print('Расчёт выполнен заново по текущей базе теми же функциями/SQL, что и гистограмма.', file=file)
        print('Пользователь определяется документом. ФИО — только подпись.', file=file)
        print('Исходные строки — контекст пассажира: они могут включать повторы, пропуски и поездки вне выбранного окна.', file=file)
        print('Все поля источников сохранены; одна JSON-строка соответствует одной исходной записи.', file=file)
        print('Карты не расширяют список перелётов: строки профилей ниже используются только в метрике карт.', file=file)
        for selection in selections:
            metric = context.metric(selection.metric)
            selected, condition = select_documents(
                metric.values, selection.x, selection.value_range, selection.lower_exclusive)
            details = defaultdict(list)
            for row in metric.details:
                if row['document'] in selected:
                    details[row['document']].append(row)
            print(f'\n{"=" * 80}\n{metric.title}\n{condition}\nНайдено документов: {len(selected)}', file=file)
            print('Правило: ' + metric.note, file=file)
            print('Ось X: ' + metric.label, file=file)
            current_document, current_table, source_count = None, None, 0
            seen = set()

            def person_header(document):
                print(f'\nДокумент: {document}', file=file)
                print(f"ФИО: {context.data.passengers.get(document) or 'не указано'}", file=file)
                print(f'Значение X: {metric.values[document]:g}', file=file)
                if details[document]:
                    print('Детали расчёта показателя:', file=file)
                    for detail in details[document]:
                        print(json.dumps(detail, ensure_ascii=False, default=str), file=file)

            for document, source_table, row_json in context.source_rows(selected, selection.metric):
                if document != current_document:
                    person_header(document)
                    current_document, current_table = document, None
                    seen.add(document)
                if source_table != current_table:
                    print(f'  Таблица: source.{source_table}', file=file)
                    current_table = source_table
                file.write('    ' + row_json + '\n')
                source_count += 1
            for document in sorted(selected - seen):
                person_header(document)
                print('Исходные строки не найдены.', file=file)
            print(f'\nВсего исходных строк в этом разделе: {source_count}', file=file)
            summary.append({'metric': selection.metric, 'condition': condition,
                            'documents': len(selected), 'source_rows': source_count})
    path = save_finished_report(temporary, path)
    print(f'{path.name}: ' + '; '.join(f"{s['condition']} — {s['documents']} документов" for s in summary), flush=True)
    return {'file': str(path), 'sections': summary, 'bytes': path.stat().st_size}


def run_searches(searches):
    try:
        connection = duckdb.connect(str(DATABASE), read_only=True)
    except duckdb.IOException as error:
        raise SystemExit(f'{error}\nЗакрой приложение, которое использует файл базы, и повтори запуск.')
    with connection:
        print('Читаю базу и рассчитываю связи пассажиров...', flush=True)
        context = SearchContext(connection)
        reports = [search(context) for search in searches]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / 'last_run.json').write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'TXT-отчёты: {OUTPUT_DIR}', flush=True)
