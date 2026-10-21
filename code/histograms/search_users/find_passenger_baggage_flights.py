"""Число перелётов с признаком багажа: поиск пассажиров по X гистограммы."""
from search_common import Selection, run_searches, write_report

Q1 = 0
Q3 = 1
OUTLIER_BOUNDARY = Q3 + 1.5 * (Q3 - Q1)  # 2.5; для целого X это X >= 3.


def get_selections():
    return [
        Selection('passenger_baggage_flights', None, lower_exclusive=OUTLIER_BOUNDARY),
    ]


def search(context):
    return write_report(context, 'find_passenger_baggage_flights.txt', get_selections())


if __name__ == '__main__':
    run_searches([search])
