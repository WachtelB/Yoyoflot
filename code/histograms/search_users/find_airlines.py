"""Число разных авиакомпаний: поиск пассажиров по X гистограммы."""
from search_common import Selection, run_searches, write_report

SELECTED_X = 1


def get_selections():
    return [
        Selection('airlines', SELECTED_X),
    ]


def search(context):
    return write_report(context, 'find_airlines.txt', get_selections())


if __name__ == '__main__':
    run_searches([search])
