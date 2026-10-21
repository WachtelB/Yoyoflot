# Поиск расхождений и отдельные выборки

Гистограммы, их SQL и результаты теперь находятся в [histograms](../histograms/README.md).

Здесь оставлены:

- `baggage_mismatches.py` и `.sql` — сравнение багажа по документу, номеру рейса и дате;
- `frequent_destinations.py` и `passenger_flights.sql` — прежняя выборка частых поездок по имени.

```powershell
py code/spy_search/baggage_mismatches.py
py code/spy_search/frequent_destinations.py
```

`frequent_destinations.py` использует прежнее сопоставление по имени. Новые метрики
в `code/histograms/` считают пассажиров по документу. Настройка `FLIGHT_THRESHOLD` сохранена.
Подробные прежние правила и ограничения сохранены в
[описании существующих скриптов](../histograms/EXISTING_SCRIPTS.md).
