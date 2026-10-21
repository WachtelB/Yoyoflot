"""Поиск расхождений по багажу между BoardingData и Sirena."""

import csv
from pathlib import Path

import duckdb


def find_baggage_mismatches(connection):
    """Выполняет SQL из соседнего файла и возвращает результат DuckDB."""
    sql_file = Path(__file__).with_suffix('.sql')
    sql = sql_file.read_text(encoding='utf-8')
    return connection.sql(sql)


def save_results(result, output_file):
    """Сохраняет все строки результата в понятный табличный TXT-файл."""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    rows = result.fetchall()

    with output_file.open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.writer(file, delimiter='\t', lineterminator='\n')
        writer.writerow(result.columns)
        writer.writerows(rows)

    return len(rows)


if __name__ == '__main__':
    script_directory = Path(__file__).resolve().parent
    database = script_directory.parents[1] / 'databaze' / 'yoyoflot.duckdb'
    output_file = script_directory / 'results' / 'baggage_mismatches.txt'

    with duckdb.connect(str(database), read_only=True) as connection:
        result = find_baggage_mismatches(connection)
        result.show(max_rows=20)
        row_count = save_results(result, output_file)

    print(f'Найдено расхождений: {row_count}')
    print(f'Результат сохранён: {output_file}')
