import json
import random
import time
import requests

API_URL = "http://127.0.0.1:8000/predict"

# Load sample transactions
with open("sample_transactions.json", "r") as f:
    transactions = json.load(f)

print(f"Loaded {len(transactions)} sample transactions. Starting stream...\n")

while True:
    txn = random.choice(transactions)
    # Remove "Class" if present, since the API doesn't expect it
    txn = {k: v for k, v in txn.items() if k != "Class"}

    try:
        response = requests.post(API_URL, json=txn)
        result = response.json()
        flag = "🚨 FRAUD" if result["prediction"] == 1 else "✅ normal"
        print(f"{flag}  | probability={result['fraud_probability']:.4f} | time={result['timestamp']}")
    except Exception as e:
        print("Error sending transaction:", e)

    time.sleep(random.uniform(1, 2))  # wait 1-2 seconds between transactions