"""Число разных направленных маршрутов у каждого документа."""
from passenger_metrics_common import Metric, run_metrics

SHOW_WINDOW = __import__('os').environ.get('SPY_NO_WINDOW') != '1'


def calculate(data):
    values = {}
    for document in data.passengers:
        routes = {flight.route for flight in data.flights.get(document, []) if flight.route}
        values[document] = len(routes) if routes else None
    return [Metric('unique_routes', 'Уникальные маршруты пассажиров', 'Число пар аэропортов', values,
                   'A → B и B → A — разные маршруты. Нет известного однозначного маршрута — нет оценки.')]


if __name__ == '__main__':
    run_metrics([calculate], SHOW_WINDOW)

