from auth import get_token
import requests

token = get_token()

headers = {
    "Authorization": f"Bearer {token}"
}

r = requests.get(
    "https://openapi.tossinvest.com/api/v1/accounts",
    headers=headers
)

print(r.status_code)
print(r.text)
