"""Запуск всех поисков: настройки X берутся из каждого мини-скрипта."""
import find_unique_routes
import find_max_flights
import find_min_flight_interval
import find_route_repetitions
import find_quick_returns
import find_airlines
import find_loyalty_cards
import find_passenger_flights
import find_passenger_baggage_flights
from search_common import run_searches

SEARCHES = [
    find_unique_routes.search,
    find_max_flights.search,
    find_min_flight_interval.search,
    find_route_repetitions.search,
    find_quick_returns.search,
    find_airlines.search,
    find_loyalty_cards.search,
    find_passenger_flights.search,
    find_passenger_baggage_flights.search,
]


if __name__ == '__main__':
    run_searches(SEARCHES)
