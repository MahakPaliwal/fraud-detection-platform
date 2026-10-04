# Real-Time Fraud Detection Platform with AI Explanation Layer

A fraud detection system that scores transactions in real time, explains *why* a transaction looks suspicious using semantic search over historical fraud cases + an LLM, and enforces secure, rate-limited, multi-tenant access — all containerized and backed by an automated CI pipeline.

## Why this project

Most fraud-scoring models return a number. This platform goes further: when a transaction is flagged, it searches a vector database of past fraud cases for similar patterns, then uses an LLM to generate a plain-English explanation for a human analyst — turning a black-box score into something a non-technical reviewer can actually act on.

## Architecture

\`\`\`
Transaction Stream (simulator)
        │
        ▼
FastAPI Scoring Service ──► Logistic Regression model (scikit-learn)
        │
        ├── Flagged as fraud?
        │       │
        │       ▼
        │   Embed transaction → Pinecone vector search (similar past fraud cases)
        │       │
        │       ▼
        │   Groq LLM (openai/gpt-oss-20b) → plain-English explanation
        │       │
        │       ▼
        │   Redis (recent alerts cache)
        │
        ▼
Secured API Gateway (per-tenant API keys + rate limiting)
\`\`\`

## Features

- **Real-time scoring** — transactions scored instantly via a FastAPI `/predict` endpoint
- **AI-generated explanations** — flagged transactions are matched against historical fraud cases (Pinecone) and explained in plain English (Groq LLM)
- **Multi-tenant security** — per-client API keys with independent rate limits
- **Containerized** — one-command startup via Docker Compose (FastAPI + Redis)
- **Automated testing** — CI pipeline (GitHub Actions) runs tests on every push

## Tech Stack

| Layer | Technology |
|---|---|
| Scoring model | scikit-learn (Logistic Regression) |
| API | FastAPI |
| Caching / alert storage | Redis |
| Vector search | Pinecone |
| LLM explanations | Groq (openai/gpt-oss-20b) |
| Auth & rate limiting | Custom FastAPI middleware |
| Containerization | Docker, Docker Compose |
| CI/CD | GitHub Actions |
| Testing | pytest |

## Dataset

Model trained on the [Credit Card Fraud Detection dataset](https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud) (ULB, via Kaggle) — 280K+ anonymized transactions, highly imbalanced (~0.17% fraud).

## Setup

### Prerequisites
- Docker Desktop
- A free [Pinecone](https://www.pinecone.io) account + API key
- A free [Groq](https://console.groq.com) account + API key

### 1. Clone and configure
```bash
git clone https://github.com/MahakPaliwal/fraud-detection-platform.git
cd fraud-detection-platform
```

Create a `.env` file:
PINECONE_API_KEY=your_key_here
GROQ_API_KEY=your_key_here


### 2. Get the dataset
Download `creditcard.csv` from [Kaggle](https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud) and place it in the project root.

### 3. Train the model
```bash
pip install -r requirements.txt
python train_model.py
```

### 4. Build the fraud case vector database
Create a Pinecone index named `fraud-cases` (dimension 384, metric cosine, serverless), then:
```bash
python build_vector_db.py
```

### 5. Run everything
```bash
docker-compose up -d
```

### 6. Test it
Visit `http://127.0.0.1:8000/docs`, authenticate with API key `key-bank-a-123`, and test the `/predict` endpoint.

### 7. (Optional) Simulate a live transaction stream
```bash
python simulate_stream.py
```

## API Reference

**`GET /health`** — health check

**`POST /predict`** — score a transaction (requires `x-api-key` header)

Example response for a flagged transaction:
```json
{
  "prediction": 1,
  "fraud_probability": 1.0,
  "explanation": "This transaction shows large negative anomalies in V14, V12, and V17, closely matching the pattern seen in 3 historical fraud cases from the same time window.",
  "similar_cases": ["Fraud case 16: ...", "Fraud case 17: ...", "Fraud case 15: ..."]
}
```

## Testing

```bash
pytest test_app.py -v
```

## Future Improvements

- Replace the synthetic stream simulator with a real Kafka-based ingestion pipeline
- Add a live dashboard (React + Recharts) for visualizing alerts in real time
- Move hardcoded API keys to a proper tenant database
- Deploy to AWS (ECS/EC2)

## Author

Mahak Paliwal
[LinkedIn](https://www.linkedin.com/in/mahak-paliwal-a739841a1)
[GitHub](https://github.com/MahakPaliwal)
