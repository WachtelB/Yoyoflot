"""Число перелётов по самому частому маршруту: поиск пассажиров по X гистограммы."""
from search_common import Selection, run_searches, write_report

Q1 = 1
Q3 = 1
OUTLIER_BOUNDARY = Q3 + 1.5 * (Q3 - Q1)  # 1; для целого X это X >= 2.


def get_selections():
    return [
        Selection('route_repetitions', None, lower_exclusive=OUTLIER_BOUNDARY),
    ]


def search(context):
    return write_report(context, 'find_route_repetitions.txt', get_selections())


if __name__ == '__main__':
    run_searches([search])
