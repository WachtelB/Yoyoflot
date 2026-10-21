// Группировка связанных пассажиров и воспроизводимое размещение групп.
const fs = require('fs');
const zlib = require('zlib');
const {UndirectedGraph} = require('graphology');
const louvain = require('graphology-communities-louvain');
const path = process.argv[2];
const data = JSON.parse(zlib.gunzipSync(fs.readFileSync(path)));
const graph = new UndirectedGraph();
data.nodes.forEach((node, id) => graph.addNode(id));
data.edges.forEach(([a, b, flights]) => graph.addEdge(a, b, {weight: flights.length}));
let seed = 42;
const rng = () => ((seed = (Math.imul(1664525, seed) + 1013904223) >>> 0) / 4294967296);
const communities = louvain(graph, {rng, getEdgeWeight: 'weight'});
const groups = new Map();
data.nodes.forEach((node, id) => {
  // Изолированные узлы размещаем общей полосой отдельно от связанных групп.
  const group = graph.degree(id) ? communities[id] : 'isolated';
  if (!groups.has(group)) groups.set(group, []);
  groups.get(group).push(id);
});
const ordered = [...groups.entries()].sort((a, b) => {
  if (a[0] === 'isolated') return 1;
  if (b[0] === 'isolated') return -1;
  return b[1].length - a[1].length;
});
const width = Math.max(60, Math.sqrt(data.nodes.length) * 3.4);
let x = 0, y = 0, rowHeight = 0, color = 0;
for (const [group, ids] of ordered) {
  // Сетка не создаёт крупные сплошные круги при общем масштабе.
  // Форма области — только раскладка, аналитического смысла она не имеет.
  const columns = Math.max(1, Math.ceil(Math.sqrt(ids.length)));
  const rows = Math.ceil(ids.length / columns);
  const spacing = 2.4;
  const groupWidth = Math.max(8, (columns - 1) * spacing + 4);
  const groupHeight = Math.max(8, (rows - 1) * spacing + 4);
  if (x + groupWidth > width) {x = 0; y += rowHeight + 5; rowHeight = 0;}
  ids.forEach((id, i) => {
    data.nodes[id][2] = x + 2 + (i % columns) * spacing;
    data.nodes[id][3] = y + 2 + Math.floor(i / columns) * spacing;
    data.nodes[id][4] = group === 'isolated' ? -1 : color;
    data.nodes[id][5] = graph.degree(id);
  });
  x += groupWidth + 5; rowHeight = Math.max(rowHeight, groupHeight); color++;
}
data.summary.communities = ordered.filter(([group]) => group !== 'isolated').length;
data.summary.isolated_nodes = data.nodes.filter(node => node[4] === -1).length;
fs.writeFileSync(path, zlib.gzipSync(JSON.stringify(data), {level: 6}));
console.log(`Размещение готово: групп ${data.summary.communities}; без связей ${data.summary.isolated_nodes}`);
