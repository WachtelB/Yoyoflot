# Код проекта

Здесь собран весь код анализа. Данные и база находятся уровнем выше, в `<project>`.

| Папка | Что в ней находится | Быстрый запуск из корня проекта |
| --- | --- | --- |
| [histograms](histograms/README.md) | Метрики пассажиров, гистограммы, SQL и поиск пассажиров по значению X | `run_histograms.cmd` или `run_user_search.cmd` |
| [passenger_graph](passenger_graph/README.md) | Построение графа совместных рейсов и интерфейс Sigma.js | `open_graph.cmd` |
| [spy_search](spy_search/README.md) | Простые отдельные проверки: багаж и частые направления | запуск нужного `.py` файла |

## Где искать конкретные задачи

- Все гистограммы: `code/histograms/*.py`.
- Общая логика гистограмм: `code/histograms/passenger_metrics_common.py`.
- Поиск людей, попавших в столбец X: `code/histograms/search_users/`.
- Код графа: `code/passenger_graph/build_passenger_graph.py`.
- Веб-интерфейс графа: `code/passenger_graph/web/`.
- Результаты графа: `code/passenger_graph/results/`.
- Проверка расхождений багажа: `code/spy_search/baggage_mismatches.py`.

Корневые `.cmd`-файлы специально оставлены рядом с базой: их можно запускать
двойным щелчком, не разыскивая основной Python-файл.
