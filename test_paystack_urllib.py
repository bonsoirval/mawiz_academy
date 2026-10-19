import os
import json
from dotenv import load_dotenv
from urllib.request import Request, urlopen
from urllib.error import HTTPError

load_dotenv(".env", override=True)

secret = os.getenv("PAYSTACK_SECRET_KEY", "").strip()

if not secret.startswith("sk_test_"):
    raise SystemExit("Paystack test secret key was not loaded.")

payload = {
    "email": "test@example.com",
    "amount": 10000,
    "currency": "NGN",
}

request = Request(
    "https://api.paystack.co/transaction/initialize",
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Authorization": f"Bearer {secret}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0",
    },
    method="POST",
)

try:
    with urlopen(request, timeout=15) as response:
        print("HTTP status:", response.status)
        print("Response:", response.read().decode("utf-8"))

except HTTPError as error:
    print("HTTP status:", error.code)
    print("Response:", error.read().decode("utf-8", errors="replace"))
