"""Число разных двухсимвольных кодов перевозчиков в номерах рейсов."""
import re
from passenger_metrics_common import Metric, run_metrics

SHOW_WINDOW = __import__('os').environ.get('SPY_NO_WINDOW') != '1'


def calculate(data):
    values, details = {}, []
    for document in data.passengers:
        codes = set()
        for flight in data.flights.get(document, []):
            match = re.fullmatch(r'([A-Z0-9]{2})[0-9]+[A-Z]?', flight.number)
            if match and any(letter.isalpha() for letter in match[1]):
                codes.add(match[1])
        values[document] = len(codes) if codes else None
        if codes:
            details.append({'document': document, 'airline_codes': ', '.join(sorted(codes))})
    return [Metric('airlines', 'Количество разных авиакомпаний у пассажира', 'Число разных авиакомпаний (по коду в номере рейса)', values,
                   'Код из номера рейса; при кодшеринге он может отличаться от фактического оператора. Реестр авиакомпаний не проверяется.',
                   details=details)]


if __name__ == '__main__':
    run_metrics([calculate], SHOW_WINDOW)

