"""Пересечения выборок search_users по документам пассажиров."""
import importlib
from collections import Counter, defaultdict
from itertools import combinations

import duckdb
from search_common import (
    DATABASE, OUTPUT_DIR, SearchContext, select_documents, save_finished_report,
)

MIN_MATCHES = 2

SEARCH_MODULES = [
    'find_unique_routes',
    'find_max_flights',
    'find_route_repetitions',
    'find_quick_returns',
    'find_loyalty_cards',
    'find_passenger_flights',
    'find_passenger_baggage_flights',
]

OUTPUT_FILE = OUTPUT_DIR / 'user_intersections_outliers.txt'


def collect_results(context, module_names):
    """Те же условия и расчёты, что у мини-скриптов, без повторной выгрузки TXT."""
    if not module_names or len(module_names) != len(set(module_names)):
        raise ValueError('SEARCH_MODULES должен быть непустым списком без повторов.')
    results = {}
    for module_name in module_names:
        module = importlib.import_module(module_name)
        users = defaultdict(list)
        conditions = []
        for selection in module.get_selections():
            metric = context.metric(selection.metric)
            documents, condition = select_documents(
                metric.values, selection.x, selection.value_range, selection.lower_exclusive)
            conditions.append(f'{metric.title}: {condition}; документов: {len(documents)}')
            for document in documents:
                users[document].append(f'{metric.title}: X = {metric.values[document]:g} ({condition})')
        results[module_name] = {'users': dict(users), 'conditions': conditions}
    return results


def find_intersections(results, minimum):
    """Вернуть документы, подходящие хотя бы под minimum разных скриптов."""
    required = len(results) if minimum is None else minimum
    if isinstance(required, bool) or not isinstance(required, int) or not 1 <= required <= len(results):
        raise ValueError('MIN_MATCHES: число от 1 до количества скриптов или None (все).')
    matches = defaultdict(list)
    for script, result in results.items():
        for document in result['users']:
            matches[document].append(script)
    selected = [(document, scripts) for document, scripts in matches.items() if len(scripts) >= required]
    selected.sort(key=lambda row: (-len(row[1]), row[0]))
    return selected, matches, required


def write_intersections(results, names, minimum=MIN_MATCHES, path=OUTPUT_FILE):
    selected, matches, required = find_intersections(results, minimum)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.txt.tmp')
    with temporary.open('w', encoding='utf-8') as file:
        print('ПЕРЕСЕЧЕНИЯ ВЫБОРОК ПАССАЖИРОВ', file=file)
        print('Выборки пересчитаны по текущей базе и текущим X в мини-скриптах.', file=file)
        print('Сравнение по документу; ФИО используется только как подпись.', file=file)
        print('Повторные строки не увеличивают число совпадений.', file=file)
        print('find_max_flights: попадания за 7 и 30 дней считаются одним скриптом (достаточно любого окна).', file=file)
        print(f'Скриптов: {len(results)}; требуется совпадений: {required}', file=file)
        print(f'Найдено документов: {len(selected)}', file=file)
        print(f'Во всех скриптах одновременно: {sum(len(scripts) == len(results) for scripts in matches.values())}', file=file)

        print('\nИСПОЛЬЗОВАННЫЕ ВЫБОРКИ', file=file)
        for script, result in results.items():
            print(f'\n{script}.py — {len(result["users"])} документов', file=file)
            for condition in result['conditions']:
                print('  ' + condition, file=file)

        print('\nРАСПРЕДЕЛЕНИЕ ПО ЧИСЛУ СОВПАВШИХ СКРИПТОВ (до фильтра)', file=file)
        for count, passengers in sorted(Counter(len(scripts) for scripts in matches.values()).items()):
            print(f'{count} скриптов: {passengers} документов', file=file)

        print('\nПОПАРНЫЕ ПЕРЕСЕЧЕНИЯ (независимо от MIN_MATCHES)', file=file)
        for first, second in combinations(results, 2):
            count = len(results[first]['users'].keys() & results[second]['users'].keys())
            print(f'{first} + {second}: {count}', file=file)

        print('\nПАССАЖИРЫ: сначала с наибольшим числом совпадений', file=file)
        for document, scripts in selected:
            print(f'\nДокумент: {document}', file=file)
            print(f'ФИО: {names.get(document) or "не указано"}', file=file)
            print(f'Совпавших скриптов: {len(scripts)} из {len(results)}', file=file)
            for script in scripts:
                print(f'  {script}.py', file=file)
                for description in results[script]['users'][document]:
                    print('    ' + description, file=file)
    saved = save_finished_report(temporary, path)
    print(f'Найдено документов: {len(selected)}; минимум совпадений: {required}')
    print(f'Отчёт: {saved}')
    return saved


def main():
    try:
        connection = duckdb.connect(str(DATABASE), read_only=True)
    except duckdb.IOException as error:
        raise SystemExit(f'{error}\nЗакрой приложение, которое использует файл базы, и повтори запуск.')
    print('Рассчитываю выборки по настройкам мини-скриптов...', flush=True)
    with connection:
        context = SearchContext(connection)
        results = collect_results(context, SEARCH_MODULES)
    write_intersections(results, context.data.passengers, MIN_MATCHES, OUTPUT_FILE)


if __name__ == '__main__':
    main()
