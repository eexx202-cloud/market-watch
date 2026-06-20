from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import requests

CLIENT_ID = os.environ["TOSS_CLIENT_ID"]
CLIENT_SECRET = os.environ["TOSS_CLIENT_SECRET"]

class Handler(BaseHTTPRequestHandler):

    def do_GET(self):

        token_res = requests.post(
            "https://openapi.tossinvest.com/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET
            }
        )

        token_text = token_res.text

        html = f"""
        <html>
        <body>
        <h1>TOKEN TEST</h1>
        <pre>{token_text}</pre>
        </body>
        </html>
        """

        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        pass

port = int(os.environ.get("PORT", 10000))
HTTPServer(("0.0.0.0", port), Handler).serve_forever()
