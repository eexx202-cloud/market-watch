import os
import requests

def get_token():

    client_id = os.getenv("TOSS_CLIENT_ID")
    client_secret = os.getenv("TOSS_CLIENT_SECRET")

    response = requests.post(
        "https://openapi.tossinvest.com/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret
        }
    )

    response.raise_for_status()

    return response.json()["access_token"]
