# Fraud Watch Dashboard

React dashboard for the Fraud Watch fraud detection platform. It shows flagged transactions as they arrive, lets an analyst inspect the AI-generated explanation for each one, and mark alerts as reviewed.

See the [root README](../README.md) for the full system overview, architecture, and backend setup.

## Features

- Live alert feed over a WebSocket, with automatic reconnect and a connection indicator
- Master-detail layout: select an alert to see its confidence, explanation, similar past cases, and raw transaction values
- Filter by severity or review status, search by amount or feature, and sort by newest or confidence
- Mark alerts as reviewed, with the status synced across open tabs
- Open-alert count, average confidence, and an activity sparkline

## Stack

React, Vite, and Recharts.

## Run locally

The backend must be running first (`docker-compose up -d` from the repository root).

```bash
npm install
npm run dev
```

Open http://localhost:5173.

## Configuration

The backend addresses and the demo API key are constants at the top of `src/App.jsx`:

```js
const API = 'http://127.0.0.1:8000';
const WS_URL = 'ws://127.0.0.1:8000/ws';
const API_KEY = 'key-bank-a-123';
```

The API key is hardcoded for local demo use only. A real deployment would put authentication in front of the dashboard instead of shipping a key in frontend code.