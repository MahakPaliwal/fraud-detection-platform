from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pickle
import redis
import json
import os
import time
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone
from groq import Groq
import hashlib
import asyncio
import redis.asyncio as aioredis
from fastapi import FastAPI, Header, HTTPException, Depends, WebSocket, WebSocketDisconnect
from datetime import datetime, timezone

load_dotenv()

app = FastAPI()

# --- CORS (allows the React dashboard to call this API) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Load model and scaler ---
with open("model.pkl", "rb") as f:
    model = pickle.load(f)

with open("scaler.pkl", "rb") as f:
    scaler = pickle.load(f)

# --- Connect to Redis ---
r = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=6379, decode_responses=True)

# --- Connect to Pinecone ---
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("fraud-cases")

# --- Load embedding model ---
embedder = SentenceTransformer("all-MiniLM-L6-v2")

# --- Connect to Groq ---
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# --- Auth / rate limiting ---
API_KEYS = {
    "key-bank-a-123": {"tenant": "bank-a", "limit_per_minute": 10},
    "key-bank-b-456": {"tenant": "bank-b", "limit_per_minute": 5},
}

def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key not in API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API key")

    tenant_info = API_KEYS[x_api_key]
    tenant = tenant_info["tenant"]
    limit = tenant_info["limit_per_minute"]

    window = int(time.time() // 60)
    key = f"ratelimit:{tenant}:{window}"
    count = r.incr(key)
    if count == 1:
        r.expire(key, 60)

    if count > limit:
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded for {tenant}. Max {limit}/minute.")

    return tenant


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
    amount = txn_dict.get("Amount", 0)
    time_val = txn_dict.get("Time", 0)
    v_features = {k: v for k, v in txn_dict.items() if k.startswith("V")}
    top_features = sorted(v_features.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
    feature_text = ", ".join([f"{k}={round(v, 2)}" for k, v in top_features])
    return (
        f"Transaction amount {round(amount, 2)}, "
        f"occurring at normalized time {round(time_val, 2)}, "
        f"with notable anomaly in features {feature_text}."
    )

def get_explanation(txn_dict):
    description = describe_transaction(txn_dict)
    cache_key = "explain:" + hashlib.sha256(description.encode()).hexdigest()

    cached = r.get(cache_key)
    if cached:
        data = json.loads(cached)
        return data["explanation"], data["similar_cases"], True

    embedding = embedder.encode(description).tolist()
    search_results = index.query(vector=embedding, top_k=3, include_metadata=True)
    similar_cases = [match["metadata"]["description"] for match in search_results["matches"]]

    prompt = f"""A new transaction was flagged as fraud:
{description}

Here are 3 similar historical fraud cases:
1. {similar_cases[0] if len(similar_cases) > 0 else "N/A"}
2. {similar_cases[1] if len(similar_cases) > 1 else "N/A"}
3. {similar_cases[2] if len(similar_cases) > 2 else "N/A"}

In 2-3 plain-English sentences, explain why this new transaction resembles these past fraud cases, for a fraud analyst reviewing this alert. Write in plain prose only, no markdown, no bullet points, no bold text, no numbered lists."""

    response = groq_client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=400,
        reasoning_effort="low",
    )
    explanation = response.choices[0].message.content

    if explanation:  # never cache an empty response
        r.setex(cache_key, 3600, json.dumps({"explanation": explanation, "similar_cases": similar_cases}))

    return explanation, similar_cases, False


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/alerts")
def get_alerts():
    ids = r.lrange("fraud_alert_ids", 0, 19)
    alerts = []
    for alert_id in ids:
        raw = r.get(f"alert:{alert_id}")
        if raw:
            alerts.append(json.loads(raw))
    return {"alerts": alerts}


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
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "transaction": txn_dict,
    }

    if prediction == 1:
        explanation, similar_cases, from_cache = get_explanation(txn_dict)
        result["explanation"] = explanation
        result["similar_cases"] = similar_cases
        result["explanation_cached"] = from_cache
        result["resolved"] = False

        alert_id = result["timestamp"]
        r.set(f"alert:{alert_id}", json.dumps(result))
        r.lpush("fraud_alert_ids", alert_id)
        r.ltrim("fraud_alert_ids", 0, 99)
        r.publish("alerts_channel", json.dumps(result))

    return result
    
@app.post("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: str, tenant: str = Depends(verify_api_key)):
    raw = r.get(f"alert:{alert_id}")
    if not raw:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert = json.loads(raw)
    alert["resolved"] = True
    r.set(f"alert:{alert_id}", json.dumps(alert))
    r.publish("alerts_channel", json.dumps(alert))
    return alert
@app.websocket("/ws")
async def websocket_alerts(websocket: WebSocket):
    await websocket.accept()
    async_redis = aioredis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"), port=6379, decode_responses=True
    )
    pubsub = async_redis.pubsub()
    await pubsub.subscribe("alerts_channel")

    async def forward():
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])

    forward_task = asyncio.create_task(forward())
    try:
        while True:
            await websocket.receive_text()  # blocks until the client disconnects
    except WebSocketDisconnect:
        pass
    finally:
        forward_task.cancel()
        await pubsub.unsubscribe("alerts_channel")
        await pubsub.aclose()
        await async_redis.aclose()