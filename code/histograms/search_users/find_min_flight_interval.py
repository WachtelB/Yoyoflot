"""Минимальный промежуток между вылетами (часы): поиск пассажиров по X гистограммы."""
from search_common import Selection, run_searches, write_report

SELECTED_X = 428
X_RANGE = None


def get_selections():
    return [
        Selection('min_flight_interval', SELECTED_X, X_RANGE),
    ]


def search(context):
    return write_report(context, 'find_min_flight_interval.txt', get_selections())


if __name__ == '__main__':
    run_searches([search])
