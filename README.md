# Fraud Watch: Real-Time Fraud Detection with AI Explanations

A fraud detection platform that scores transactions in real time, explains why each flagged transaction looks suspicious, and pushes alerts to a live analyst dashboard where they can be reviewed and resolved. Access is secured with per-tenant API keys and Redis-backed rate limits.

When a transaction is flagged, the system searches a vector database of past fraud cases for similar patterns, then asks an LLM to write a short plain-English explanation for the analyst. This turns a bare fraud score into something a human reviewer can act on.

## Demo


<img width="1896" height="817" alt="image" src="https://github.com/user-attachments/assets/d16379ee-5723-40c2-a757-a0bc42a24ec1" />





<img width="1916" height="820" alt="image" src="https://github.com/user-attachments/assets/b00da9e8-d538-4673-8526-05eeb5c65cc8" />



**Live demo:** https://fraud-detection-platform-alpha.vercel.app/

The hosted page replays alerts captured from the full system (FastAPI, Redis, Pinecone, Groq running locally in Docker). The backend isn't deployed, so alerts there are a replay. To run the full stack, see [Setup](#setup).

## Features

- **Real-time scoring:** a FastAPI `/predict` endpoint scores each transaction with a scikit-learn model.
- **AI-generated explanations:** flagged transactions are matched against historical fraud cases in Pinecone, and a Groq-hosted LLM explains the match.
- **Explanation caching:** explanations are cached in Redis by a hash of the transaction description, so repeated patterns skip the LLM call.
- **Live dashboard:** a React app receives new alerts over a WebSocket the moment they are flagged, with automatic reconnect.
- **Analyst workflow:** alerts can be filtered (critical, elevated, open, resolved), searched, sorted, and marked as reviewed. The status syncs across open tabs.
- **Persistent alerts:** alerts and review status are stored in Redis with append-only persistence on a Docker volume, so they survive restarts.
- **Multi-tenant security:** per-client API keys with independent per-minute rate limits. Counters live in Redis, so they survive restarts and are shared across API instances.
- **Containerized:** the backend and Redis start with one Docker Compose command.
- **Automated testing:** GitHub Actions runs the test suite on every push.

## Architecture

1. A transaction stream (simulator) sends transactions to the FastAPI service.
2. Every request passes through the API gateway layer, which checks the `x-api-key` header and enforces the tenant's rate limit using a Redis counter.
3. The service scales the transaction and scores it with a Logistic Regression model.
4. If the transaction is flagged as fraud:
   - It is turned into a text description and embedded with a sentence-transformer model.
   - Pinecone returns the three most similar historical fraud cases.
   - Redis is checked for a cached explanation. On a miss, a Groq LLM writes one from the similar cases, and the result is cached.
   - The alert is stored in Redis and published to a pub/sub channel.
5. A WebSocket endpoint forwards every published alert to all connected dashboards.
6. The React dashboard displays the alert instantly. Marking an alert reviewed calls the API, which updates Redis and publishes the change to all open dashboards.

## Tech Stack

| Layer | Technology |
|---|---|
| Scoring model | scikit-learn (Logistic Regression) |
| API | FastAPI |
| Live updates | WebSockets backed by Redis pub/sub |
| Alert storage, cache, rate limits | Redis (append-only persistence) |
| Vector search | Pinecone, sentence-transformers (all-MiniLM-L6-v2) |
| LLM explanations | Groq (openai/gpt-oss-20b) |
| Auth and rate limiting | Custom FastAPI dependency |
| Dashboard | React, Vite, Recharts |
| Containerization | Docker, Docker Compose |
| CI | GitHub Actions, pytest |

## Design Decisions

- **Redis pub/sub for the WebSocket feed.** `/predict` is a synchronous endpoint and cannot write to sockets directly. Publishing to a channel decouples scoring from delivery and still works if more than one API instance is run.
- **Exact-match explanation cache.** The cache key is a hash of the full transaction description. A coarser key would hit more often, but the LLM text quotes specific numbers, so reusing it for a different transaction could show wrong values.
- **Fixed-window rate limiting in Redis.** Each tenant gets a counter per minute, incremented atomically. It is simple and shared across instances. The trade-off is that a burst straddling a window boundary can briefly exceed the limit.
- **Recall over precision.** The model uses balanced class weights because missing real fraud is the costly mistake. The explanation layer exists to help analysts triage the resulting false positives.
- **Pinned scikit-learn.** The model is pickled, so the training environment and the container must use the same scikit-learn version (1.5.1). A mismatch crashes prediction at runtime.
- **Raw values in the demo stream.** The simulator replays unscaled transactions, and the API scales each one exactly once before scoring. This keeps live alerts in the same units as the historical cases in the vector database.
- **UTC timestamps.** Alerts carry timezone-aware UTC timestamps, so the dashboard shows correct relative times in any timezone.
- **CPU-only PyTorch in Docker.** The container has no GPU, and the default CUDA build adds several GB to every build.

## Model Performance

Trained on the [Credit Card Fraud Detection dataset](https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud) (ULB, via Kaggle): 280K+ anonymized transactions, about 0.17% fraud. On the held-out test set the model reaches about 92% recall and about 6% precision for the fraud class. That is the expected trade-off at this class imbalance with balanced weights. The model is a deliberately simple baseline, and the engineering effort in this project is in the system around it.

## Setup

### Prerequisites

- Python 3.12
- Docker Desktop
- Node.js 20 or newer
- A free [Pinecone](https://www.pinecone.io) account and API key
- A free [Groq](https://console.groq.com) account and API key

### 1. Clone and configure

```bash
git clone https://github.com/MahakPaliwal/fraud-detection-platform.git
cd fraud-detection-platform
```

Create a `.env` file in the project root:

```
PINECONE_API_KEY=your_key_here
GROQ_API_KEY=your_key_here
```

### 2. Get the dataset

Download `creditcard.csv` from Kaggle and place it in the project root. It is not stored in this repository because of its size.

### 3. Train the model

```bash
pip install -r requirements.txt
python train_model.py
```

The repository already includes trained `model.pkl` and `scaler.pkl` files that match the pinned scikit-learn version. Retrain only if you change the model. Retraining also regenerates `sample_transactions.json`, the raw transactions used by the simulator.

### 4. Build the fraud case vector database

In the Pinecone console, create a serverless index named `fraud-cases` with dimension 384 and the cosine metric, then run:

```bash
python build_vector_db.py
```

### 5. Start the backend

```bash
docker-compose up -d --build
```

The first build downloads PyTorch and can take a while. Later rebuilds are fast because the dependency layers are cached. To wipe stored alerts and start fresh, run `docker-compose down -v`.

### 6. Start the dashboard

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

### 7. Generate traffic

```bash
python simulate_stream.py
```

New alerts appear in the dashboard as they are flagged. The simulator waits 7 to 10 seconds between requests to stay under the demo tenant's rate limit.

## API Reference

| Endpoint | Description |
|---|---|
| `GET /health` | Health check |
| `POST /predict` | Score a transaction. Requires an `x-api-key` header. |
| `GET /alerts` | Latest flagged alerts |
| `POST /alerts/{id}/resolve` | Mark an alert as reviewed. Requires an `x-api-key` header. |
| `WS /ws` | Live stream of new and updated alerts |

Interactive docs are available at http://127.0.0.1:8000/docs.

Example `/predict` response for a flagged transaction:

```json
{
  "prediction": 1,
  "fraud_probability": 1.0,
  "explanation": "The transaction shows large negative deviations in V14 and V17, matching the pattern in three historical fraud cases.",
  "similar_cases": ["Fraud case 16: ...", "Fraud case 17: ...", "Fraud case 15: ..."],
  "explanation_cached": false,
  "resolved": false
}
```

## Testing

```bash
pytest test_app.py -v
```

The tests cover the health check and authentication behavior. They run automatically in CI on every push.

## Known Limitations

- **Demo credentials.** API keys are hardcoded in the backend and the dashboard. A real deployment would use a tenant database and a login in front of the dashboard.
- **Open read endpoints.** `GET /alerts` and `/ws` are not authenticated, alerts are not scoped per tenant, and CORS allows all origins. Fine for local use, not for production.
- **Simulated traffic.** The stream replays 20 sample transactions rather than a real feed.
- **Unvalidated explanations.** The LLM explanations are grounded in retrieved similar cases and instructed not to infer time of day, but they are not otherwise checked for factual accuracy.
- **Fixed-window rate limits.** A burst across a window boundary can briefly exceed a tenant's limit.
- **Anonymized features.** Most model inputs are PCA components (V1 to V28), so explanations can point to which features deviate but not what they mean in business terms.
- - **Replay-only hosted demo.** The public link is a static replay of captured alerts. The full backend runs locally via Docker Compose.

## Future Improvements

- Replace the simulator with a Kafka-based ingestion pipeline
- Move tenants and API keys into a database, scope alerts per tenant, and add dashboard authentication
- Add SHAP-based feature attributions alongside the LLM explanation
- Deploy the backend to the cloud (the hosted demo is currently a replay)

## Author

Mahak Paliwal
