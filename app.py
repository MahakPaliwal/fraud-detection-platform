from fastapi import FastAPI
from pydantic import BaseModel
import pickle
import redis
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone
from groq import Groq
from fastapi import Header, HTTPException, Depends
import time

# Hardcoded tenants for this MVP (in a real system, these would live in a database)
API_KEYS = {
    "key-bank-a-123": {"tenant": "bank-a", "limit_per_minute": 10},
    "key-bank-b-456": {"tenant": "bank-b", "limit_per_minute": 5},
}

# In-memory request tracking: {tenant: [(timestamp1), (timestamp2), ...]}
request_log = {}

def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key not in API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API key")

    tenant_info = API_KEYS[x_api_key]
    tenant = tenant_info["tenant"]
    limit = tenant_info["limit_per_minute"]

    now = time.time()
    timestamps = request_log.get(tenant, [])
    # Keep only requests from the last 60 seconds
    timestamps = [t for t in timestamps if now - t < 60]

    if len(timestamps) >= limit:
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded for {tenant}. Max {limit}/minute.")

    timestamps.append(now)
    request_log[tenant] = timestamps

    return tenant
load_dotenv()

app = FastAPI()

# Load model and scaler
with open("model.pkl", "rb") as f:
    model = pickle.load(f)

with open("scaler.pkl", "rb") as f:
    scaler = pickle.load(f)

# Connect to Redis
import os
r = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=6379, decode_responses=True)

# Connect to Pinecone
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("fraud-cases")

# Load embedding model (same one used to build the vector DB)
embedder = SentenceTransformer("all-MiniLM-L6-v2")

# Connect to Groq
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))


class Transaction(BaseModel):
    Time: float
    V1: float; V2: float; V3: float; V4: float; V5: float
    V6: float; V7: float; V8: float; V9: float; V10: float
    V11: float; V12: float; V13: float; V14: float; V15: float
    V16: float; V17: float; V18: float; V19: float; V20: float
    V21: float; V22: float; V23: float; V24: float; V25: float
    V26: float; V27: float; V28: float
    Amount: float


def describe_transaction(txn_dict):
    """Same description logic used when building the vector DB."""
    amount = txn_dict.get("Amount", 0)
    time = txn_dict.get("Time", 0)
    v_features = {k: v for k, v in txn_dict.items() if k.startswith("V")}
    top_features = sorted(v_features.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
    feature_text = ", ".join([f"{k}={round(v, 2)}" for k, v in top_features])
    return (
        f"Transaction amount {round(amount, 2)}, "
        f"occurring at normalized time {round(time, 2)}, "
        f"with notable anomaly in features {feature_text}."
    )


def get_explanation(txn_dict):
    """Search Pinecone for similar past fraud cases, then ask Groq to explain."""
    description = describe_transaction(txn_dict)
    embedding = embedder.encode(description).tolist()

    search_results = index.query(vector=embedding, top_k=3, include_metadata=True)
    similar_cases = [match["metadata"]["description"] for match in search_results["matches"]]

    prompt = f"""A new transaction was flagged as fraud:
{description}

Here are 3 similar historical fraud cases:
1. {similar_cases[0] if len(similar_cases) > 0 else "N/A"}
2. {similar_cases[1] if len(similar_cases) > 1 else "N/A"}
3. {similar_cases[2] if len(similar_cases) > 2 else "N/A"}

In 2-3 plain-English sentences, explain why this new transaction resembles these past fraud cases, for a fraud analyst reviewing this alert."""

    response = groq_client.chat.completions.create(
    model="openai/gpt-oss-20b",
    messages=[{"role": "user", "content": prompt}],
    max_tokens=400,
    reasoning_effort="low",
)

    return response.choices[0].message.content, similar_cases


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/predict")
def predict(transaction: Transaction, tenant: str = Depends(verify_api_key)):
    txn_dict = transaction.dict()
    data = [list(txn_dict.values())]
    scaled = scaler.transform(data)
    prediction = model.predict(scaled)[0]
    probability = model.predict_proba(scaled)[0][1]

    result = {
        "prediction": int(prediction),
        "fraud_probability": round(float(probability), 4),
        "timestamp": datetime.utcnow().isoformat(),
        "transaction": txn_dict,
    }

    if prediction == 1:
        explanation, similar_cases = get_explanation(txn_dict)
        result["explanation"] = explanation
        result["similar_cases"] = similar_cases

        r.lpush("fraud_alerts", json.dumps(result))
        r.ltrim("fraud_alerts", 0, 99)

    return result