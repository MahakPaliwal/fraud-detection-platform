import os
import json
import pandas as pd
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone

load_dotenv()

# Connect to Pinecone
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("fraud-cases")

# Load embedding model (small, fast, 384-dim — matches your index dimension)
embedder = SentenceTransformer("all-MiniLM-L6-v2")

# Load sample transactions (we'll use the fraud ones as our "historical case library")
# Load fraud cases directly from the original dataset
df = pd.read_csv("creditcard.csv")
fraud_df = df[df["Class"] == 1].drop(columns=["Class"]).head(30)  # take 30 real fraud cases
fraud_cases = fraud_df.to_dict(orient="records")
print(f"Found {len(fraud_cases)} fraud cases to index.")

def describe_transaction(txn, case_id):
    """Turn a numeric transaction into a short text description for embedding."""
    amount = txn.get("Amount", 0)
    time = txn.get("Time", 0)
    # Flag the most extreme V-features as "notable patterns"
    v_features = {k: v for k, v in txn.items() if k.startswith("V")}
    top_features = sorted(v_features.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
    feature_text = ", ".join([f"{k}={round(v, 2)}" for k, v in top_features])
    return (
        f"Fraud case {case_id}: transaction amount {round(amount, 2)}, "
        f"occurring at normalized time {round(time, 2)}, "
        f"with notable anomaly in features {feature_text}."
    )

vectors_to_upsert = []
for i, case in enumerate(fraud_cases):
    description = describe_transaction(case, i)
    embedding = embedder.encode(description).tolist()
    vectors_to_upsert.append({
        "id": f"fraud-case-{i}",
        "values": embedding,
        "metadata": {"description": description}
    })
    print(f"Prepared case {i}: {description}")

# Upload to Pinecone
index.upsert(vectors=vectors_to_upsert)
print(f"\nUploaded {len(vectors_to_upsert)} fraud case embeddings to Pinecone.")