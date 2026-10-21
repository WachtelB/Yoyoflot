"""Построить полный граф общих вылетов и открыть его в Sigma.js."""
import argparse
import gzip
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import duckdb

DIRECTORY = Path(__file__).resolve().parent
PROJECT = DIRECTORY.parents[1]
HISTOGRAMS = DIRECTORY.parent / 'histograms'
DATABASE = PROJECT / 'databaze' / 'yoyoflot.duckdb'
RESULTS = DIRECTORY / 'results' / 'passenger_graph'
OPEN_VIEWER = True


def prepare_graph(connection):
    """В базе создаются только временные таблицы."""
    connection.execute((HISTOGRAMS / 'prepare_passenger_metrics.sql').read_text(encoding='utf-8'))
    connection.execute((DIRECTORY / 'prepare_graph.sql').read_text(encoding='utf-8'))


def export_graph(connection, path):
    """Компактные массивы уменьшают размер файла и время загрузки браузером."""
    nodes = connection.execute('SELECT document, full_name FROM graph_nodes ORDER BY node_id').fetchall()
    flights = connection.execute('''
        SELECT flight_number, CAST(flight_date AS VARCHAR), CAST(flight_time AS VARCHAR),
               origin, destination, passengers FROM graph_flights ORDER BY flight_id
    ''').fetchall()
    edges = connection.execute('SELECT source, target, flights FROM graph_edges ORDER BY source, target').fetchall()

    def count(sql):
        return connection.execute(sql).fetchone()[0]

    summary = {
        'created_at': datetime.now().isoformat(timespec='seconds'),
        'nodes': len(nodes), 'edges': len(edges), 'flights': len(flights),
        'memberships': count('SELECT COUNT(*) FROM graph_memberships'),
        'shared_flights': count('SELECT COUNT(*) FROM graph_flights WHERE passengers > 1'),
        'pair_flight_matches': sum(len(row[2]) for row in edges),
        'max_weight': max((len(row[2]) for row in edges), default=0),
        'excluded_events_missing_time_or_route': count('''
            SELECT COUNT(*) FROM passenger_events
            WHERE flight_time IS NULL OR origin IS NULL OR destination IS NULL
        '''),
        'conflicting_document_flight_dates': count('SELECT COUNT(*) FROM graph_conflicts'),
        'ambiguous_tickets': count('SELECT COUNT(*) FROM ticket_owners WHERE owner_count > 1'),
        'rule': 'flight_number + departure_date + departure_time + origin + destination',
        'sources': ['boarding_data', 'sirena', 'boarding_passes'],
        'note': 'Совпадение записей одного вылета не подтверждает фактическую посадку.',
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, 'wt', encoding='utf-8') as file:
        json.dump({'summary': summary, 'nodes': nodes, 'flights': flights, 'edges': edges},
                  file, ensure_ascii=False, separators=(',', ':'))
    return summary


def node_executable():
    found = shutil.which('node')
    if found:
        return found
    bundled = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
    if bundled.exists():
        return str(bundled)
    raise SystemExit('Не найден Node.js для размещения графа. Установи Node.js и повтори запуск.')


def build_graph():
    if not (DIRECTORY / 'layout_bundle.cjs').exists() or not (DIRECTORY / 'web/app.js').exists():
        raise SystemExit('Не найдена сборка Sigma.js. Инструкция: code/passenger_graph/README.md.')
    RESULTS.mkdir(parents=True, exist_ok=True)
    temporary = RESULTS / 'graph.building.json.gz'
    print('Собираю узлы и пары внутри каждого вылета...', flush=True)
    try:
        connection = duckdb.connect(str(DATABASE), read_only=True)
    except duckdb.IOException as error:
        raise SystemExit(f'{error}\nЗакрой приложение, которое использует файл базы, и повтори запуск.')
    with connection:
        prepare_graph(connection)
        summary = export_graph(connection, temporary)
    print(f"Узлов: {summary['nodes']}; связей: {summary['edges']}. Размещаю группы...", flush=True)
    subprocess.run([node_executable(), str(DIRECTORY / 'layout_bundle.cjs'), str(temporary)], check=True)
    with gzip.open(temporary, 'rt', encoding='utf-8') as file:
        summary = json.load(file)['summary']
    temporary.replace(RESULTS / 'graph.json.gz')
    (RESULTS / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Граф сохранён: {RESULTS}', flush=True)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-open', action='store_true', help='Построить граф без запуска просмотрщика.')
    args = parser.parse_args()
    build_graph()
    if OPEN_VIEWER and not args.no_open:
        from serve_graph import main
        main(open_browser=True)
