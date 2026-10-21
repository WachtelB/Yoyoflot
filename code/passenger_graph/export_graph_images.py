"""Экспортировать две презентационные картинки графа совместных перелётов."""

from __future__ import annotations

import gzip
import json
import math
from collections import defaultdict, deque
from pathlib import Path

import matplotlib

matplotlib.use('Agg')

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.patches import Circle, FancyBboxPatch


DIRECTORY = Path(__file__).resolve().parent
GRAPH_FILE = DIRECTORY / 'results' / 'passenger_graph' / 'graph.json.gz'
OUTPUT = DIRECTORY / 'results' / 'graph_gallery'

BACKGROUND = '#071820'
PANEL = '#0d252e'
TEXT = '#eef8f7'
MUTED = '#9ab3b8'
EDGE = '#6bc8c5'
PALETTE = np.array([
    '#2aa198', '#4e8fd3', '#b678c4', '#d7a13a',
    '#63ad7f', '#d06f78', '#7a91ca', '#55bac0',
])


def load_graph():
    if not GRAPH_FILE.exists():
        raise SystemExit(f'Не найден готовый граф: {GRAPH_FILE}')
    with gzip.open(GRAPH_FILE, 'rt', encoding='utf-8') as file:
        return json.load(file)


def add_header(fig, title, subtitle, cards):
    fig.text(0.055, 0.945, title, color=TEXT, fontsize=25, fontweight='bold', va='top')
    fig.text(0.055, 0.905, subtitle, color=MUTED, fontsize=12, va='top')
    x = 0.055
    for value, label in cards:
        fig.text(x, 0.842, value, color=TEXT, fontsize=18, fontweight='bold', va='top')
        fig.text(x, 0.812, label, color=MUTED, fontsize=9, va='top')
        x += 0.145


def finish_figure(fig, path, note):
    fig.text(0.055, 0.035, note, color=MUTED, fontsize=8.5)
    fig.savefig(path, dpi=180, facecolor=BACKGROUND, bbox_inches='tight', pad_inches=0.12)
    plt.close(fig)


def export_all_connections(data):
    nodes = data['nodes']
    edges = data['edges']
    degrees = np.zeros(len(nodes), dtype=np.int32)
    pairs = np.empty((len(edges), 2), dtype=np.int32)
    for index, (source, target, _) in enumerate(edges):
        pairs[index] = source, target
        degrees[source] += 1
        degrees[target] += 1

    connected = np.flatnonzero(degrees)
    coordinates = np.asarray([[node[2], node[3]] for node in nodes], dtype=np.float32)
    segments = coordinates[pairs]
    communities = np.asarray([node[4] for node in nodes], dtype=np.int64)
    colors = PALETTE[np.mod(communities[connected], len(PALETTE))]

    fig = plt.figure(figsize=(20, 11.25), facecolor=BACKGROUND)
    ax = fig.add_axes((0.045, 0.09, 0.91, 0.69), facecolor=PANEL)
    ax.add_collection(LineCollection(
        segments,
        colors=(0.37, 0.72, 0.74, 0.045),
        linewidths=0.10,
        rasterized=True,
    ))
    sizes = 0.7 + np.minimum(np.log2(degrees[connected] + 1), 7) * 0.16
    ax.scatter(
        coordinates[connected, 0], coordinates[connected, 1],
        s=sizes, c=colors, alpha=0.86, linewidths=0, rasterized=True,
    )
    margin = 12
    ax.set_xlim(coordinates[connected, 0].min() - margin, coordinates[connected, 0].max() + margin)
    ax.set_ylim(coordinates[connected, 1].max() + margin, coordinates[connected, 1].min() - margin)
    ax.set_aspect('equal', adjustable='datalim')
    ax.set_axis_off()

    add_header(
        fig,
        'Граф совместных перелётов',
        'Связь появляется, если два документа встретились хотя бы на одном одинаковом вылете',
        [
            (f'{len(connected):,}'.replace(',', ' '), 'связанных пассажиров'),
            (f'{len(edges):,}'.replace(',', ' '), 'пар пассажиров'),
            (f"{data['summary']['shared_flights']:,}".replace(',', ' '), 'общих вылетов'),
            (f"{data['summary']['communities']:,}".replace(',', ' '), 'групп Louvain'),
        ],
    )
    finish_figure(
        fig,
        OUTPUT / '01_one_shared_flight.png',
        'Цвет показывает структурную группу по связям. Размер точки ограничен и не является мерой подозрительности. '
        'Изолированные документы скрыты.',
    )


def repeated_components(edges):
    adjacency = defaultdict(set)
    for source, target, flights in edges:
        if len(flights) < 2:
            continue
        adjacency[source].add(target)
        adjacency[target].add(source)

    seen = set()
    components = []
    for start in sorted(adjacency):
        if start in seen:
            continue
        queue = deque([start])
        seen.add(start)
        members = []
        while queue:
            node = queue.popleft()
            members.append(node)
            for neighbor in sorted(adjacency[node]):
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        components.append(sorted(members))
    components.sort(key=lambda values: (-len(values), values[0]))
    return adjacency, components


def export_two_connections(data):
    nodes = data['nodes']
    repeated = [edge for edge in data['edges'] if len(edge[2]) >= 2]
    adjacency, components = repeated_components(repeated)
    component_of = {}
    positions = {}

    columns = 17
    cell_width, cell_height = 2.25, 1.90
    for component_index, members in enumerate(components):
        row, column = divmod(component_index, columns)
        center_x = column * cell_width
        center_y = -row * cell_height
        component_of.update({node: component_index for node in members})
        radius = 0.52 if len(members) <= 2 else 0.62
        for index, node in enumerate(members):
            angle = math.pi / 2 + 2 * math.pi * index / len(members)
            if len(members) == 2:
                angle = math.pi if index == 0 else 0
            positions[node] = (center_x + radius * math.cos(angle), center_y + radius * math.sin(angle))

    fig = plt.figure(figsize=(20, 11.25), facecolor=BACKGROUND)
    ax = fig.add_axes((0.045, 0.09, 0.91, 0.69), facecolor=PANEL)

    for component_index, members in enumerate(components):
        row, column = divmod(component_index, columns)
        center_x = column * cell_width
        center_y = -row * cell_height
        color = PALETTE[component_index % len(PALETTE)]
        ax.add_patch(Circle(
            (center_x, center_y), 0.79,
            facecolor=color, edgecolor=color, alpha=0.055, linewidth=0.55,
        ))

    segments = [[positions[source], positions[target]] for source, target, _ in repeated]
    ax.add_collection(LineCollection(segments, colors=EDGE, linewidths=1.35, alpha=0.78))

    repeated_nodes = sorted(positions)
    point_colors = [PALETTE[component_of[node] % len(PALETTE)] for node in repeated_nodes]
    point_sizes = [15 + 6 * len(adjacency[node]) for node in repeated_nodes]
    ax.scatter(
        [positions[node][0] for node in repeated_nodes],
        [positions[node][1] for node in repeated_nodes],
        s=point_sizes, c=point_colors, edgecolors='#dff7f4', linewidths=0.25, zorder=3,
    )

    rows = math.ceil(len(components) / columns)
    ax.set_xlim(-1.2, (columns - 1) * cell_width + 1.2)
    ax.set_ylim(-(rows - 1) * cell_height - 1.15, 1.15)
    ax.set_aspect('equal')
    ax.set_axis_off()

    size_counts = defaultdict(int)
    for component in components:
        size_counts[len(component)] += 1
    add_header(
        fig,
        'Повторные совместные перелёты',
        'Связь остаётся, только если одна пара документов встретилась на двух одинаковых вылетах',
        [
            (f'{len(repeated_nodes):,}'.replace(',', ' '), 'пассажиров'),
            (f'{len(repeated):,}'.replace(',', ' '), 'повторных пар'),
            (f'{len(components):,}'.replace(',', ' '), 'отдельных компонентов'),
            (f"{size_counts[2]} / {size_counts[3]} / {size_counts[4]}", 'групп по 2 / 3 / 4'),
        ],
    )
    finish_figure(
        fig,
        OUTPUT / '02_two_shared_flights.png',
        'Каждый светлый круг — отдельная связная группа. Линия означает два общих вылета. '
        'Все имена и конкретные рейсы доступны при выборе узла в интерактивной версии.',
    )


def write_gallery(data):
    summary = data['summary']
    html = f'''<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Галерея графа совместных перелётов</title>
  <style>
    :root {{ color-scheme: dark; font-family: Segoe UI,Arial,sans-serif; background:#071820; color:#eef8f7; }}
    * {{ box-sizing:border-box; }} body {{ margin:0; background:radial-gradient(circle at 20% 0,#153640,#071820 46%); }}
    header {{ max-width:1380px; margin:auto; padding:54px 32px 28px; }}
    .tag {{ color:#79d2cc; font-size:12px; font-weight:700; letter-spacing:.16em; }}
    h1 {{ font-size:clamp(32px,5vw,64px); line-height:1.02; margin:14px 0; max-width:900px; }}
    header p {{ color:#a6bdc2; max-width:760px; font-size:17px; line-height:1.6; }}
    main {{ max-width:1380px; margin:auto; padding:10px 32px 70px; display:grid; gap:30px; }}
    article {{ background:#0d252e; border:1px solid #20424c; border-radius:24px; overflow:hidden; box-shadow:0 24px 70px #0006; }}
    .copy {{ display:flex; align-items:center; justify-content:space-between; gap:24px; padding:24px 28px; }}
    h2 {{ margin:0 0 7px; font-size:25px; }} .copy p {{ margin:0; color:#9ab3b8; }}
    a.button {{ color:#071820; background:#79d2cc; text-decoration:none; font-weight:700; padding:12px 18px; border-radius:12px; white-space:nowrap; }}
    a.image {{ display:block; background:#071820; }} img {{ display:block; width:100%; height:auto; }}
    footer {{ max-width:1380px; margin:auto; padding:0 32px 45px; color:#75939a; font-size:13px; }}
    @media(max-width:700px) {{ .copy {{ align-items:flex-start; flex-direction:column; }} header,main,footer {{ padding-left:18px;padding-right:18px; }} }}
  </style>
</head>
<body>
  <header>
    <div class="tag">CATCH THE SPIES · PASSENGER GRAPH</div>
    <h1>Две глубины одного графа</h1>
    <p>Первая версия показывает все пары пассажиров с общим вылетом. Вторая оставляет только устойчивые связи, повторившиеся на двух разных вылетах. Данные остаются на компьютере.</p>
  </header>
  <main>
    <article>
      <div class="copy"><div><h2>Один общий вылет</h2><p>{summary['edges']:,} связей · обзор всей структуры</p></div><a class="button" href="/?minimum=1">Открыть интерактивно</a></div>
      <a class="image" href="/exports/01_one_shared_flight.png"><img src="/exports/01_one_shared_flight.png" alt="Граф с минимум одним общим вылетом"></a>
    </article>
    <article>
      <div class="copy"><div><h2>Два общих вылета</h2><p>278 связей · повторные встречи тех же пар</p></div><a class="button" href="/?minimum=2">Открыть интерактивно</a></div>
      <a class="image" href="/exports/02_two_shared_flights.png"><img src="/exports/02_two_shared_flights.png" alt="Граф с двумя общими вылетами"></a>
    </article>
  </main>
  <footer>Связь означает совпадение номера рейса, даты, времени и аэропортов. Она не доказывает знакомство пассажиров или фактическую посадку.</footer>
</body>
</html>'''
    html = html.replace(f"{summary['edges']:,}", f"{summary['edges']:,}".replace(',', ' '))
    (OUTPUT / 'index.html').write_text(html, encoding='utf-8')


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    data = load_graph()
    print('Рисую граф с минимум одним общим вылетом...', flush=True)
    export_all_connections(data)
    print('Рисую граф с двумя общими вылетами...', flush=True)
    export_two_connections(data)
    write_gallery(data)
    print(f'Готово: {OUTPUT}', flush=True)


if __name__ == '__main__':
    main()
