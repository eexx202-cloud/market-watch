from http.server import HTTPServer, BaseHTTPRequestHandler
from bs4 import BeautifulSoup
import requests
import os

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):

        try:
            url = "https://finance.naver.com/sise/"

            headers = {
                "User-Agent": "Mozilla/5.0"
            }

            r = requests.get(url, headers=headers, timeout=10)

            soup = BeautifulSoup(r.text, "html.parser")

            kospi = soup.select_one("#KOSPI_now")
            kosdaq = soup.select_one("#KOSDAQ_now")

            kospi_text = kospi.text.strip() if kospi else "조회실패"
            kosdaq_text = kosdaq.text.strip() if kosdaq else "조회실패"

            msg = f"""
KOSPI : {kospi_text}

KOSDAQ : {kosdaq_text}
"""

        except Exception as e:
            msg = f"ERROR : {e}"

        self.send_response(200)
        self.end_headers()
        self.wfile.write(msg.encode())

port = int(os.environ.get("PORT", 10000))

server = HTTPServer(("0.0.0.0", port), Handler)

print(f"Server started on {port}")

server.serve_forever()
import requests
from bs4 import BeautifulSoup
