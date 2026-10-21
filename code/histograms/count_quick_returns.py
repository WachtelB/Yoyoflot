"""Последовательные A → B → A без повторного использования перелётов."""
from passenger_metrics_common import Metric, run_metrics

SHOW_WINDOW = __import__('os').environ.get('SPY_NO_WINDOW') != '1'
RETURN_HOURS = 48


def calculate(data):
    if RETURN_HOURS <= 0:
        raise ValueError('RETURN_HOURS должно быть положительным')
    values, details = {}, []
    for document in data.passengers:
        flights = data.flights.get(document, [])
        values[document] = None
        if len(flights) < 2 or any(f.departure is None or f.route is None for f in flights):
            continue
        flights = sorted(flights, key=lambda f: (f.departure, f.number))
        if len({f.departure for f in flights}) != len(flights):
            continue  # При одновременных вылетах порядок неоднозначен.
        count, index = 0, 0
        while index + 1 < len(flights):
            first, second = flights[index:index + 2]
            hours = (second.departure - first.departure).total_seconds() / 3600
            if (first.origin != first.destination and first.route == second.route[::-1]
                    and 0 < hours <= RETURN_HOURS):
                count += 1
                details.append({'document': document, 'origin': first.origin, 'destination': first.destination,
                                'outbound': first.departure, 'return_departure': second.departure,
                                'outbound_flight': first.number, 'return_flight': second.number, 'hours': hours})
                index += 2
            else:
                index += 1
        values[document] = count
    return [Metric('quick_returns', f'Быстрые возвращения: до {RETURN_HOURS:g} часов', 'Число возвращений', values,
                   'A → B → A, каждый перелёт используется один раз. Интервал между вылетами по местным часам. Неполные последовательности исключены.',
                   details=details)]


if __name__ == '__main__':
    run_metrics([calculate], SHOW_WINDOW)

