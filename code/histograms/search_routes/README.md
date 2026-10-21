# Поиск маршрутов по значению X

В `find_routes_by_flight_count.py` задаются:

```python
ROUTE_TYPE = 'city'   # либо 'airport'
SELECTED_X = 2        # либо список: [2, 3, 4]
```

Скрипт находит пары с указанным числом уникальных рейсов и сохраняет полные
исходные строки в `results/route_search/find_routes_by_flight_count.txt`.

Запуск из `<project>`:

```powershell
.\.venv\Scripts\python.exe code\histograms\search_routes\find_routes_by_flight_count.py
```
