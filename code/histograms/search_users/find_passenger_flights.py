"""Число перелётов (уникальных билетов): поиск пассажиров по X гистограммы."""
from search_common import Selection, run_searches, write_report

Q1 = 1
Q3 = 3
OUTLIER_BOUNDARY = Q3 + 1.5 * (Q3 - Q1)  # 6; для целого X это X >= 7.


def get_selections():
    return [
        Selection('passenger_flights', None, lower_exclusive=OUTLIER_BOUNDARY),
    ]


def search(context):
    return write_report(context, 'find_passenger_flights.txt', get_selections())


if __name__ == '__main__':
    run_searches([search])
