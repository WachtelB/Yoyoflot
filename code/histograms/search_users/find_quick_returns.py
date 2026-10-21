"""Число быстрых возвращений: поиск пассажиров по X гистограммы."""
from search_common import Selection, run_searches, write_report

Q1 = 0
Q3 = 0
OUTLIER_BOUNDARY = Q3 + 1.5 * (Q3 - Q1)  # 0; для целого X это X >= 1.

def get_selections():
    return [
        Selection('quick_returns', None, lower_exclusive=OUTLIER_BOUNDARY),
    ]


def search(context):
    return write_report(context, 'find_quick_returns.txt', get_selections())


if __name__ == '__main__':
    run_searches([search])
