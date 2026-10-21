import os
import requests
from dotenv import load_dotenv

load_dotenv()

secret_key = os.getenv("PAYSTACK_SECRET_KEY", "").strip()

if not secret_key.startswith("sk_test_"):
    raise SystemExit(
        "A valid Paystack test secret key is not configured."
    )

url = "https://api.paystack.co/transaction/initialize"

headers = {
    "Authorization": f"Bearer {secret_key}",
    "Content-Type": "application/json",
}

payload = {
    "email": "test@example.com",
    "amount": 10000,  # NGN 100.00 in kobo
    "currency": "NGN",
}

try:
    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=15,
    )

    print("HTTP status:", response.status_code)
    print("Paystack response:", response.text)

except requests.RequestException as error:
    print("Connection error:", error)
