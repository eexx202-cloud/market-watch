TOKEN_RESULT = f"""
STATUS={r.status_code}
<br><br>
HEADERS={dict(r.headers)}
<br><br>
BODY={r.text}
"""
