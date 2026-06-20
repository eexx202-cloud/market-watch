from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import requests

CLIENT_ID = os.environ["TOSS_CLIENT_ID"]
CLIENT_SECRET = os.environ["TOSS_CLIENT_SECRET"]

def get_token():
    r = requests.post(
        "https://openapi.tossinvest.com/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET
        }
    )

    print("TOKEN RESPONSE")
    print(r.text)

    return r.json().get("access_token")


class Handler(BaseHTTPRequestHandler):

    def do_GET(self):

        token = get_token()

        r = requests.get(
            "https://openapi.tossinvest.com/api/v1/prices",
            headers={
                "Authorization": f"Bearer {token}"
            },
            params={
                "symbols": "005930"
            }
        )

        print("PRICE RESPONSE")
        print(r.text)

        html = f"""
        <html>
        <body>
        <h1>TOSS TEST</h1>
        <pre>{r.text}</pre>
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
