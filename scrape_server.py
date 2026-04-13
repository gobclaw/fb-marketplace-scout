from http.server import HTTPServer, BaseHTTPRequestHandler
import os, json

OUTFILE = os.path.expanduser('~/marketplace-scraper/scrape_results.txt')

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        data = self.rfile.read(length).decode('utf-8')
        body = json.loads(data)
        term = body.get('term', '')
        lines = body.get('lines', '')
        mode = body.get('mode', 'append')
        
        m = 'w' if mode == 'rewrite' else 'a'
        with open(OUTFILE, m) as f:
            f.write(f'\n=== {term} ===\n{lines}\n')
        
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(b'ok')
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def log_message(self, format, *args):
        pass

print(f'Server starting on port 9876, writing to {OUTFILE}')
HTTPServer(('127.0.0.1', 9876), Handler).serve_forever()
