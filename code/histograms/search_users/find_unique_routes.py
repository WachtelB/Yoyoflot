"""Число уникальных маршрутов: поиск пассажиров по X гистограммы."""
from search_common import Selection, run_searches, write_report

Q1 = 1
Q3 = 2
OUTLIER_BOUNDARY = Q3 + 1.5 * (Q3 - Q1)  # 3.5; для целого X это X >= 4.


def get_selections():
    return [
        Selection('unique_routes', None, lower_exclusive=OUTLIER_BOUNDARY),
    ]


def search(context):
    return write_report(context, 'find_unique_routes.txt', get_selections())


if __name__ == '__main__':
    run_searches([search])
