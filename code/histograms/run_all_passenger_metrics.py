"""Все пассажирские гистограммы: девять скриптов, десять графиков."""
from passenger_metrics_common import run_metrics
from count_unique_routes import calculate as unique_routes
from count_max_flights import calculate as max_flights
from count_min_flight_interval import calculate as min_interval
from count_route_repetitions import calculate as repetitions
from count_quick_returns import calculate as quick_returns
from count_airlines import calculate as airlines
from count_loyalty_cards import calculate as loyalty_cards
from count_passenger_flights import count_passenger_flights, save_report as save_flight_report
from count_passenger_baggage_flights import count_baggage_flights, save_report as save_baggage_report

SHOW_WINDOW = __import__('os').environ.get('SPY_NO_WINDOW') != '1'


def main(show_window=SHOW_WINDOW):
    run_metrics([unique_routes, max_flights, min_interval, repetitions,
                 quick_returns, airlines, loyalty_cards], show_window, include_cards=True,
                additional_reports=[(count_passenger_flights, save_flight_report),
                                    (count_baggage_flights, save_baggage_report)])


if __name__ == '__main__':
    main()

