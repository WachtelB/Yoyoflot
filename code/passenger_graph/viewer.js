import Sigma from 'sigma';
import {EdgeLineProgram} from 'sigma/rendering';
import {UndirectedGraph} from 'graphology';
import forceAtlas2 from 'graphology-layout-forceatlas2';

// Данные: nodes = [документ, ФИО, x, y, группа, степень],
// edges = [номер узла A, номер узла B, номера общих вылетов].
const $ = id => document.getElementById(id);
const format = value => value.toLocaleString('ru-RU');
const palette = ['#247f85', '#5088bc', '#aa7bb8', '#c09042', '#579b77', '#c37477', '#6783aa', '#57a9aa'];
let data, renderer, graph, focus = null, busy = false;
let visibleEdges = [], weights, degrees;
const requestedMinimum = Number(new URLSearchParams(window.location.search).get('minimum'));
const initialMinimum = Number.isInteger(requestedMinimum) && requestedMinimum >= 1 ? requestedMinimum : 1;
let filters = {minimum: initialMinimum, from: '', to: '', hideIsolated: true};

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function button(text, action, className) {
  const node = element('button', text, className);
  node.addEventListener('click', action);
  return node;
}
function pause() { return new Promise(resolve => setTimeout(resolve, 0)); }
function setBusy(value, message = 'Подготавливаю граф…') {
  busy = value;
  $('loading').hidden = !value;
  $('loading-text').textContent = message;
  $('apply').disabled = value;
  $('overview').disabled = value;
}
function fullName(id) { return data.nodes[id][1] || 'ФИО не указано'; }
function shortName(id) { return fullName(id).split(' / ')[0]; }
function relevantFlights(edgeId) {
  return data.edges[edgeId][2].filter(id => {
    const date = data.flights[id][1];
    return (!filters.from || date >= filters.from) && (!filters.to || date <= filters.to);
  });
}

async function calculateFilters() {
  visibleEdges = [];
  weights = new Uint32Array(data.edges.length);
  degrees = new Uint32Array(data.nodes.length);
  for (let id = 0; id < data.edges.length; id++) {
    const edge = data.edges[id];
    const count = filters.from || filters.to ? relevantFlights(id).length : edge[2].length;
    if (count >= filters.minimum) {
      visibleEdges.push(id);
      weights[id] = count;
      degrees[edge[0]]++;
      degrees[edge[1]]++;
    }
    if (id % 50000 === 0) await pause();
  }
}

async function renderGraph() {
  setBusy(true, focus === null ? 'Рисую все узлы и связи…' : 'Показываю попутчиков…');
  await pause();
  if (renderer) { renderer.kill(); renderer = null; }
  if (graph) { graph.clear(); graph = null; }
  graph = new UndirectedGraph();
  const localNodes = new Set();
  let edgeIds = visibleEdges;
  if (focus !== null) {
    localNodes.add(focus);
    edgeIds = visibleEdges.filter(id => {
      const [a, b] = data.edges[id];
      if (a !== focus && b !== focus) return false;
      localNodes.add(a); localNodes.add(b);
      return true;
    });
  }
  const nodeIds = focus === null
    ? data.nodes.map((_, id) => id).filter(id => !filters.hideIsolated || degrees[id] > 0)
    : [...localNodes];
  for (let i = 0; i < nodeIds.length; i++) {
    const id = nodeIds[i], node = data.nodes[id];
    let x = node[2], y = node[3];
    if (focus !== null) {
      const angle = i * 2.399963229728653, radius = 10 + Math.sqrt(i) * 3;
      x = id === focus ? 0 : radius * Math.cos(angle);
      y = id === focus ? 0 : radius * Math.sin(angle);
    }
    graph.addNode(String(id), {
      x, y, label: `${shortName(id)} · ${node[0]}`,
      // В общем виде точки намеренно маленькие: плотные сообщества не должны
      // выглядеть как один огромный круг. В окружении пассажира они крупнее.
      size: focus === null ? 0.55 + Math.min(1.15, Math.log2(1 + degrees[id]) * 0.12) : (id === focus ? 9 : 4),
      color: id === focus ? '#d78b30' : node[4] < 0 ? '#b5c3c8' : palette[node[4] % palette.length],
      forceLabel: id === focus,
    });
    if (i % 10000 === 0) await pause();
  }
  for (let i = 0; i < edgeIds.length; i++) {
    const id = edgeIds[i], [a, b] = data.edges[id];
    graph.addEdgeWithKey(String(id), String(a), String(b), {
      weight: weights[id],
      color: weights[id] > 1 ? '#087d77' : focus !== null ? '#365f83' : '#617a94',
      size: 1, label: `${weights[id]} общих вылетов`,
    });
    if (i % 20000 === 0) await pause();
  }
  // Раскладка небольшого окружения; весь граф уже размещён при подготовке.
  if (focus !== null && graph.order > 1 && graph.order <= 2000) {
    forceAtlas2.assign(graph, {iterations: 45, settings: {
      barnesHutOptimize: true, gravity: 1, scalingRatio: 8, slowDown: 2,
    }});
  }
  renderer = new Sigma(graph, $('graph'), {
    defaultEdgeType: 'line', edgeProgramClasses: {line: EdgeLineProgram},
    renderLabels: $('labels').checked || focus !== null,
    renderEdgeLabels: false, labelFont: 'Segoe UI, Arial',
    labelSize: 11, labelDensity: 0.03, labelRenderedSizeThreshold: 5,
    hideEdgesOnMove: true, enableEdgeEvents: true,
    minCameraRatio: 0.0005, maxCameraRatio: 4,
    stagePadding: 28, allowInvalidContainer: false,
  });
  renderer.on('clickNode', ({node}) => { if (!busy) selectPassenger(Number(node)); });
  renderer.on('clickEdge', ({edge}) => showEdge(Number(edge)));
  $('view-title').textContent = focus === null ? 'Все пассажиры' : 'Пассажир и его прямые связи';
  $('status').textContent = `На экране: ${format(graph.order)} узлов · ${format(graph.size)} связей` +
    (graph.order === 0 ? ' · Измените фильтры или включите узлы без связей' : '');
  setBusy(false);
}

function showPassenger(id) {
  const panel = $('details');
  panel.replaceChildren(element('h2', shortName(id), 'passenger-name'));
  panel.append(element('p', `Документ: ${data.nodes[id][0]}`));
  if (fullName(id) !== shortName(id)) panel.append(element('p', fullName(id), 'muted'));
  panel.append(element('span', `${format(degrees[id])} попутчиков по фильтрам`, 'badge'));
  panel.append(element('p', 'Связи ниже учитывают выбранные даты и минимум общих вылетов.', 'muted'));
  const neighbors = visibleEdges.filter(edgeId => {
    const [a, b] = data.edges[edgeId];
    return a === id || b === id;
  }).sort((a, b) => weights[b] - weights[a] || a - b);
  if (!neighbors.length) {
    panel.append(element('p', 'Совпадений по текущим фильтрам нет. Узел сохранён в графе.', 'muted'));
    return;
  }
  const list = element('div');
  let loaded = 0;
  const more = button('Показать ещё', appendPage, 'more');
  function appendPage() {
    const end = Math.min(loaded + 50, neighbors.length);
    for (; loaded < end; loaded++) {
      const edgeId = neighbors[loaded], [a, b] = data.edges[edgeId], other = a === id ? b : a;
      const row = element('div', undefined, 'neighbor');
      row.append(button(`${shortName(other)} · ${data.nodes[other][0]}`, () => selectPassenger(other)));
      row.append(button(`Общие вылеты: ${weights[edgeId]} →`, () => showEdge(edgeId), 'edge-button'));
      list.append(row);
    }
    more.hidden = loaded >= neighbors.length;
    more.textContent = `Показать ещё (${neighbors.length - loaded})`;
  }
  panel.append(list, more);
  appendPage();
}

async function selectPassenger(id) {
  if (busy) return;
  focus = id;
  $('search-results').replaceChildren();
  try {
    await renderGraph();
    showPassenger(id);
  } catch (error) { showError(error); }
}

function showEdge(id) {
  const [a, b] = data.edges[id], flights = relevantFlights(id);
  const panel = $('details');
  panel.replaceChildren(element('h2', 'Общие вылеты'));
  panel.append(button(`${shortName(a)} · ${data.nodes[a][0]}`, () => selectPassenger(a), 'wide'));
  panel.append(button(`${shortName(b)} · ${data.nodes[b][0]}`, () => selectPassenger(b), 'wide'));
  panel.append(element('span', `${flights.length} вылетов по фильтрам`, 'badge'));
  for (const flightId of flights) {
    const [number, date, time, from, to, passengers] = data.flights[flightId];
    const card = element('div', undefined, 'flight-card');
    card.append(element('strong', `${from} → ${to}`));
    card.append(element('p', `${date} · ${time.slice(0, 5)} · ${number}`));
    card.append(element('small', `${passengers} документов на этом вылете в данных`));
    panel.append(card);
  }
  panel.append(element('p', 'Время вылета взято из источников без пересчёта часового пояса. Разные номера кодшеринга не объединяются.', 'muted'));
}

let searchTimer;
$('search').addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    if (!data) return;
    const query = $('search').value.trim().toUpperCase(), compact = query.replace(/\s+/g, '');
    const box = $('search-results');
    box.replaceChildren();
    if (query.length < 2) return;
    let found = 0;
    for (let id = 0; id < data.nodes.length; id++) {
      const [doc, name] = data.nodes[id];
      if (!doc.includes(compact) && !(name || '').toUpperCase().includes(query)) continue;
      if (found++ >= 30) break;
      const result = button(shortName(id), () => selectPassenger(id));
      result.append(element('small', doc));
      box.append(result);
    }
    if (!found) box.append(element('p', 'Совпадений нет', 'muted'));
    if (found > 30) box.append(element('p', 'Показаны первые 30. Уточните поиск.', 'muted'));
  }, 180);
});

$('apply').addEventListener('click', async () => {
  if (busy) return;
  const minimum = Number($('minimum').value), from = $('date-from').value, to = $('date-to').value;
  if (!Number.isInteger(minimum) || minimum < 1 || (from && to && from > to)) {
    $('filter-error').textContent = 'Укажите целый минимум от 1 и даты в правильном порядке.';
    return;
  }
  $('filter-error').textContent = '';
  filters = {minimum, from, to, hideIsolated: $('hide-isolated').checked};
  try {
    setBusy(true, 'Применяю фильтры…');
    await calculateFilters();
    await renderGraph();
    if (focus !== null) showPassenger(focus);
    else $('details').replaceChildren(element('h2', 'Выберите пассажира'), element('p', 'Нажмите на узел или воспользуйтесь поиском.', 'muted'));
  } catch (error) { showError(error); }
});
$('overview').addEventListener('click', async () => {
  if (busy) return;
  focus = null;
  try {
    await renderGraph();
    $('details').replaceChildren(element('h2', 'Выберите пассажира'), element('p', 'Все пассажиры доступны через поиск, включая узлы без связей.', 'muted'));
  } catch (error) { showError(error); }
});
$('labels').addEventListener('change', () => renderer?.setSetting('renderLabels', $('labels').checked || focus !== null));
$('zoom-in').addEventListener('click', () => renderer?.getCamera().animatedZoom({duration: 200}));
$('zoom-out').addEventListener('click', () => renderer?.getCamera().animatedUnzoom({duration: 200}));
$('reset-camera').addEventListener('click', () => renderer?.getCamera().animatedReset({duration: 300}));

function showError(error) {
  console.error(error);
  setBusy(false);
  $('status').textContent = 'Ошибка отображения';
  $('filter-error').textContent = `Не удалось показать граф: ${error.message}. Для Sigma.js нужен браузер с WebGL.`;
}

async function start() {
  setBusy(true, 'Загружаю полный граф…');
  try {
    const response = await fetch('/data.json');
    if (!response.ok) throw new Error(`Загрузка данных: HTTP ${response.status}`);
    data = await response.json();
    $('total-nodes').textContent = format(data.summary.nodes);
    $('total-edges').textContent = format(data.summary.edges);
    $('minimum').max = Math.max(1, data.summary.max_weight);
    filters.minimum = Math.min(filters.minimum, data.summary.max_weight || 1);
    $('minimum').value = String(filters.minimum);
    const audit = $('audit');
    const lines = [
      'Совпадают номер рейса, дата, время, аэропорты отправления и прибытия.',
      'Источники: BoardingData, Sirena и посадочные талоны, однозначно связанные по билету.',
      `Узлов без связей: ${format(data.summary.isolated_nodes)}.`,
      `Событий без времени или однозначного маршрута: ${format(data.summary.excluded_events_missing_time_or_route)}.`,
      `Групп с противоречивым временем: ${format(data.summary.conflicting_document_flight_dates)}.`,
      `Неоднозначных билетов для привязки посадочных талонов: ${format(data.summary.ambiguous_tickets)}.`,
      `Расчёт: ${data.summary.created_at.replace('T', ' ')}.`,
    ];
    lines.forEach(line => audit.append(element('p', line)));
    if (data.flights.length) {
      $('date-from').min = $('date-to').min = data.flights[0][1];
      $('date-from').max = $('date-to').max = data.flights[data.flights.length - 1][1];
    }
    await calculateFilters();
    await renderGraph();
  } catch (error) { showError(error); }
}
start();
