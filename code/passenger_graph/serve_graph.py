"""Локальный просмотрщик: только 127.0.0.1, без доступа к файлу базы."""
import argparse
import json
import mimetypes
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

DIRECTORY = Path(__file__).resolve().parent
RESULTS = DIRECTORY / 'results' / 'passenger_graph'
GALLERY = DIRECTORY / 'results' / 'graph_gallery'


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        route = urlsplit(self.path).path
        files = {
            '/': DIRECTORY / 'web/index.html',
            '/app.js': DIRECTORY / 'web/app.js',
            '/style.css': DIRECTORY / 'web/style.css',
            '/app.js.LEGAL.txt': DIRECTORY / 'web/app.js.LEGAL.txt',
            '/data.json': RESULTS / 'graph.json.gz',
            '/summary.json': RESULTS / 'summary.json',
            '/gallery': GALLERY / 'index.html',
            '/gallery/': GALLERY / 'index.html',
            '/exports/01_one_shared_flight.png': GALLERY / '01_one_shared_flight.png',
            '/exports/02_two_shared_flights.png': GALLERY / '02_two_shared_flights.png',
        }
        path = files.get(route)
        if path is None or not path.is_file():
            self.send_error(404)
            return
        self.send_response(200)
        content_type = 'application/json' if route == '/data.json' else mimetypes.guess_type(path.name)[0]
        self.send_header('Content-Type', content_type or 'application/octet-stream')
        self.send_header('Content-Length', str(path.stat().st_size))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if route == '/data.json':
            self.send_header('Content-Encoding', 'gzip')
        self.end_headers()
        with path.open('rb') as file:
            while chunk := file.read(1024 * 1024):
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break

    def log_message(self, *args):
        pass


def main(open_browser=True, port=0, start_path='/'):
    if not (RESULTS / 'graph.json.gz').exists():
        raise SystemExit('Сначала запусти code/passenger_graph/build_passenger_graph.py.')
    with ThreadingHTTPServer(('127.0.0.1', port), Handler) as server:
        base_url = f'http://127.0.0.1:{server.server_port}'
        url = base_url + start_path
        (RESULTS / 'viewer.json').write_text(json.dumps({'url': url}), encoding='utf-8')
        print(f'Граф: {url}\nОставь это окно работающим. Для остановки нажми Ctrl+C.', flush=True)
        if open_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print('\nПросмотрщик остановлен.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--gallery', action='store_true', help='Открыть галерею двух готовых вариантов.')
    args = parser.parse_args()
    main(not args.no_browser, args.port, '/gallery' if args.gallery else '/')
