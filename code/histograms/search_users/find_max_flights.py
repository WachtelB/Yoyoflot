"""Поиск пассажиров по максимуму перелётов за 7 и 30 дней."""
from search_common import Selection, run_searches, write_report

Q1_7_DAYS, Q3_7_DAYS = 1, 1
Q1_30_DAYS, Q3_30_DAYS = 1, 2
OUTLIER_BOUNDARY_7_DAYS = Q3_7_DAYS + 1.5 * (Q3_7_DAYS - Q1_7_DAYS)   # X > 1
OUTLIER_BOUNDARY_30_DAYS = Q3_30_DAYS + 1.5 * (Q3_30_DAYS - Q1_30_DAYS)  # X > 3.5


def get_selections():
    return [
        Selection('max_flights_7_days', None, lower_exclusive=OUTLIER_BOUNDARY_7_DAYS),
        Selection('max_flights_30_days', None, lower_exclusive=OUTLIER_BOUNDARY_30_DAYS),
    ]


def search(context):
    return write_report(context, 'find_max_flights.txt', get_selections())


if __name__ == '__main__':
    run_searches([search])
