// Сборка локальных библиотек: нужна только при изменении интерфейса.
const esbuild = require('esbuild');
esbuild.buildSync({entryPoints: ['viewer.js'], bundle: true, minify: true,
  outfile: 'web/app.js', platform: 'browser', target: 'es2020', legalComments: 'linked'});
esbuild.buildSync({entryPoints: ['layout.cjs'], bundle: true, minify: true,
  outfile: 'layout_bundle.cjs', platform: 'node', target: 'node18', legalComments: 'linked'});
