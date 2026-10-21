"""Минимальный промежуток между последовательными вылетами по местным часам."""
from passenger_metrics_common import Metric, run_metrics

SHOW_WINDOW = __import__('os').environ.get('SPY_NO_WINDOW') != '1'


def calculate(data):
    values, details = {}, []
    for document in data.passengers:
        flights = data.flights.get(document, [])
        values[document] = None
        if len(flights) < 2 or any(f.departure is None for f in flights):
            continue
        flights = sorted(flights, key=lambda f: (f.departure, f.number))
        first, second = min(zip(flights, flights[1:]), key=lambda pair: pair[1].departure - pair[0].departure)
        values[document] = (second.departure - first.departure).total_seconds() / 3600
        details.append({'document': document, 'first_flight': first.number, 'first_departure': first.departure,
                        'second_flight': second.number, 'second_departure': second.departure,
                        'hours': values[document]})
    return [Metric('min_flight_interval', 'Минимальный промежуток между вылетами', 'Промежуток, часы', values,
                   'Разница местных часов, без поправки на часовые пояса. Нужны минимум 2 перелёта и время всех известных вылетов.',
                   integer=False, details=details)]


if __name__ == '__main__':
    run_metrics([calculate], SHOW_WINDOW)

