from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import requests

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):

        try:
            url = "https://finance.naver.com/sise/"

            headers = {
                "User-Agent": "Mozilla/5.0"
            }

            r = requests.get(
                url,
                headers=headers,
                timeout=10
            )

            msg = r.text[:3000]

        except Exception as e:
            msg = "ERROR : " + str(e)

        self.send_response(200)
        self.end_headers()
        self.wfile.write(msg.encode())

port = int(os.environ.get("PORT", 10000))

server = HTTPServer(("0.0.0.0", port), Handler)

print(f"Server started on {port}")

server.serve_forever()
