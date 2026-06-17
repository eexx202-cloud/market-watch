import os

print("ACCOUNT:", bool(os.environ.get("TOSS_ACCOUNT")))
print("CLIENT_ID:", bool(os.environ.get("TOSS_CLIENT_ID")))
print("CLIENT_SECRET:", bool(os.environ.get("TOSS_CLIENT_SECRET")))

while True:
    pass
