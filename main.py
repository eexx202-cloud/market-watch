from http.server import HTTPServer, BaseHTTPRequestHandler
import os

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()

        msg = """
KOSPI WATCH
KOSDAQ WATCH

Next Step Ready
"""
        self.wfile.write(msg.encode())

port = int(os.environ.get("PORT", 10000))

server = HTTPServer(("0.0.0.0", port), Handler)

print(f"Server started on {port}")

server.serve_forever()
