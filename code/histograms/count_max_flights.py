"""Максимум перелётов в скользящем окне из 7 или 30 календарных дней."""
from datetime import timedelta
from passenger_metrics_common import Metric, run_metrics

SHOW_WINDOW = __import__('os').environ.get('SPY_NO_WINDOW') != '1'
WINDOW_DAYS = (7, 30)


def calculate(data):
    metrics = []
    for days in WINDOW_DAYS:
        if days < 1:
            raise ValueError('Размер окна должен быть положительным')
        values, details = {}, []
        for document in data.passengers:
            dates = sorted(flight.date for flight in data.flights.get(document, []))
            left, maximum, best_start = 0, 0, None
            for right, date in enumerate(dates):
                while (date - dates[left]).days >= days:
                    left += 1
                if right - left + 1 > maximum:
                    maximum, best_start = right - left + 1, dates[left]
            values[document] = maximum if dates else None
            if best_start is not None:
                details.append({'document': document, 'start_inclusive': best_start,
                                'end_exclusive': best_start + timedelta(days=days), 'flights': maximum})
        metrics.append(Metric(f'max_flights_{days}_days', f'Максимум перелётов за {days} дней',
                              'Максимальное число перелётов в окне', values,
                              f'Скользящее окно: {days} календарных дней по датам источников; правая граница не включается.',
                              details=details))
    return metrics


if __name__ == '__main__':
    run_metrics([calculate], SHOW_WINDOW)

