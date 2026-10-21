"""Число перелётов по самому частому направленному маршруту."""
from collections import Counter
from passenger_metrics_common import Metric, run_metrics

SHOW_WINDOW = __import__('os').environ.get('SPY_NO_WINDOW') != '1'


def calculate(data):
    values, details = {}, []
    for document in data.passengers:
        routes = Counter(f.route for f in data.flights.get(document, []) if f.route)
        maximum = max(routes.values()) if routes else None
        values[document] = maximum
        for (origin, destination), count in sorted(routes.items()):
            if count == maximum:
                details.append({'document': document, 'origin': origin, 'destination': destination, 'flights': count})
    return [Metric('route_repetitions', 'Самый частый маршрут пассажира', 'Число перелётов по маршруту', values,
                   'Считаются все перелёты по наиболее частому маршруту, включая первый. Неизвестные и конфликтующие маршруты исключены.',
                   details=details)]


if __name__ == '__main__':
    run_metrics([calculate], SHOW_WINDOW)

