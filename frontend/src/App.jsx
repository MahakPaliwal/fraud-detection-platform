import { useState, useEffect, useRef } from 'react';
import { LineChart, Line, ResponsiveContainer } from 'recharts';
import './App.css';

const API = 'http://127.0.0.1:8000';
const WS_URL = 'ws://127.0.0.1:8000/ws';
const API_KEY = 'key-bank-a-123';

function topFeatures(txn) {
  return Object.entries(txn)
    .filter(([k]) => k.startsWith('V'))
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
    .slice(0, 3);
}

function timeAgo(timestamp, now) {
  const diff = Math.max(0, Math.floor((now - new Date(timestamp)) / 1000));
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

function App() {
  const [alerts, setAlerts] = useState([]);
  const [history, setHistory] = useState([]);
  const [clock, setClock] = useState(new Date());
  const [connected, setConnected] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState('newest');
  const [readIds, setReadIds] = useState(new Set());
  const [actionMsg, setActionMsg] = useState('');
  const knownIds = useRef(new Set());
  const newSinceTick = useRef(0);

  const resolveAlert = async (timestamp) => {
    try {
      const res = await fetch(`${API}/alerts/${encodeURIComponent(timestamp)}/resolve`, {
        method: 'POST',
        headers: { 'x-api-key': API_KEY },
      });
      if (res.ok) {
        setAlerts((prev) =>
          prev.map((a) => (a.timestamp === timestamp ? { ...a, resolved: true } : a))
        );
        setActionMsg('');
      } else {
        setActionMsg(
          res.status === 429
            ? 'Rate limit reached, try again in a minute.'
            : 'Could not update alert.'
        );
      }
    } catch {
      setActionMsg('Could not reach the API.');
    }
  };

  useEffect(() => {
    let ws;
    let retryTimer;
    let closed = false;

    const loadAlerts = async () => {
      try {
        const res = await fetch(`${API}/alerts`);
        const data = await res.json();
        data.alerts.forEach((a) => knownIds.current.add(a.timestamp));
        setAlerts(data.alerts);
      } catch {
        // the next reconnect will sync again
      }
    };

    const connect = () => {
      ws = new WebSocket(WS_URL);

      ws.onopen = () => {
        setConnected(true);
        loadAlerts(); // catch up on anything missed while disconnected
      };

      ws.onmessage = (event) => {
        const incoming = JSON.parse(event.data);
        const isNew = !knownIds.current.has(incoming.timestamp);
        if (isNew) {
          knownIds.current.add(incoming.timestamp);
          newSinceTick.current += 1;
        }
        setAlerts((prev) =>
          isNew
            ? [incoming, ...prev].slice(0, 100)
            : prev.map((a) => (a.timestamp === incoming.timestamp ? incoming : a))
        );
      };

      ws.onclose = () => {
        setConnected(false);
        if (!closed) retryTimer = setTimeout(connect, 2000);
      };
    };

    connect();

    const tick = setInterval(() => {
      setHistory((prev) => [...prev.slice(-19), { count: newSinceTick.current }]);
      newSinceTick.current = 0;
    }, 3000);
    const clockInterval = setInterval(() => setClock(new Date()), 1000);

    return () => {
      closed = true;
      clearTimeout(retryTimer);
      clearInterval(tick);
      clearInterval(clockInterval);
      if (ws) ws.close();
    };
  }, []);

  const withSeverity = alerts.map((a) => ({
    ...a,
    severity: a.fraud_probability >= 0.9 ? 'critical' : 'elevated',
  }));

  let filtered = withSeverity.filter((a) => {
    if (filter === 'critical' || filter === 'elevated') return a.severity === filter;
    if (filter === 'open') return !a.resolved;
    if (filter === 'resolved') return a.resolved;
    return true;
  });

  if (search.trim()) {
    const q = search.trim().toLowerCase();
    filtered = filtered.filter((a) =>
      a.transaction.Amount.toFixed(2).includes(q) ||
      topFeatures(a.transaction).some(([k]) => k.toLowerCase().includes(q))
    );
  }

  filtered = [...filtered].sort((a, b) =>
    sort === 'newest'
      ? new Date(b.timestamp) - new Date(a.timestamp)
      : b.fraud_probability - a.fraud_probability
  );

  const selected = filtered.find((a) => a.timestamp === selectedId) || filtered[0] || null;

  const handleSelect = (timestamp) => {
    setSelectedId(timestamp);
    setReadIds((prev) => new Set(prev).add(timestamp));
  };

  const openCount = alerts.filter((a) => !a.resolved).length;

  const avgConfidence = alerts.length
    ? Math.round((alerts.reduce((sum, a) => sum + a.fraud_probability, 0) / alerts.length) * 100)
    : 0;

  return (
    <div className="shell">
      <div className="topbar">
        <h1>
          <span
            className={`live-dot ${connected ? '' : 'offline'}`}
            title={connected ? 'Live: connected' : 'Reconnecting...'}
          />{' '}
          Fraud Watch
        </h1>
        <span className="clock">{clock.toLocaleTimeString()}</span>
      </div>

      <div className="stats-strip">
        <div className="stat"><span className="stat-value">{openCount}</span><span className="stat-label">open alerts</span></div>
        <div className="stat-divider" />
        <div className="stat"><span className="stat-value">{avgConfidence}%</span><span className="stat-label">avg. confidence</span></div>
        <div className="stat-divider" />
        <div className="spark-cell">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={history}>
              <Line type="monotone" dataKey="count" stroke="#4ADE80" strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="workspace">
        <div className="list-pane">
          <div className="toolbar">
            <button className={`tab ${filter === 'all' ? 'active' : ''}`} onClick={() => setFilter('all')}>All</button>
            <button className={`tab ${filter === 'critical' ? 'active' : ''}`} onClick={() => setFilter('critical')}>Critical</button>
            <button className={`tab ${filter === 'elevated' ? 'active' : ''}`} onClick={() => setFilter('elevated')}>Elevated</button>
            <button className={`tab ${filter === 'open' ? 'active' : ''}`} onClick={() => setFilter('open')}>Open</button>
            <button className={`tab ${filter === 'resolved' ? 'active' : ''}`} onClick={() => setFilter('resolved')}>Resolved</button>
            <select className="sort-select" value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="newest">Newest</option>
              <option value="confidence">Confidence</option>
            </select>
          </div>
          <div className="toolbar">
            <input
              className="search-input"
              placeholder="Search amount or feature (e.g. V14)"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          <div className="list-scroll">
            {filtered.length === 0 && (
              <p style={{ padding: '1rem', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                No alerts match. Run the simulator to generate some.
              </p>
            )}
            {filtered.map((a) => (
              <div
                key={a.timestamp}
                className={`list-row ${selected?.timestamp === a.timestamp ? 'active' : ''} ${a.resolved ? 'resolved' : ''}`}
                onClick={() => handleSelect(a.timestamp)}
              >
                <span className={`severity-dot ${a.severity}`} />
                <div className="row-main">
                  <div className="row-amount tooltip" data-tooltip="How unusual this amount is vs. normal">
                    {a.transaction.Amount.toFixed(2)}
                  </div>
                  <div className="row-meta">{timeAgo(a.timestamp, clock)} · {(a.fraud_probability * 100).toFixed(0)}%</div>
                </div>
                {!readIds.has(a.timestamp) && <span className="unread-dot" />}
              </div>
            ))}
          </div>
        </div>

        <div className="detail-pane">
          {!selected && <p className="detail-empty">Select an alert to see its details.</p>}

          {selected && (
            <>
              <div className="detail-header">
                <span className="detail-amount tooltip" data-tooltip="How unusual this amount is vs. normal">
                  {selected.transaction.Amount.toFixed(2)}
                </span>
                <span className="detail-time">{new Date(selected.timestamp).toLocaleString()}</span>
              </div>

              <span className={`severity-tag ${selected.severity}`}>
                {selected.severity === 'critical' ? 'Critical match' : 'Elevated risk'}
              </span>

              {selected.resolved ? (
                <span className="resolved-badge">✓ Reviewed</span>
              ) : (
                <button className="resolve-btn" onClick={() => resolveAlert(selected.timestamp)}>
                  Mark reviewed
                </button>
              )}
              {actionMsg && (
                <p className="stat-label" style={{ color: 'var(--elevated)' }}>{actionMsg}</p>
              )}

              <div className="confidence-row">
                <span className="stat-label">{(selected.fraud_probability * 100).toFixed(1)}% match confidence</span>
                <div className="confidence-bar">
                  <div className="confidence-fill" style={{ width: `${selected.fraud_probability * 100}%` }} />
                </div>
              </div>

              <div className="signature">
                {topFeatures(selected.transaction).map(([k, v]) => (
                  <span key={k} className="chip">{k} {v > 0 ? '▲' : '▼'} {v.toFixed(1)}</span>
                ))}
              </div>

              <p className="section-label">Why this was flagged</p>
              <p className="explanation">{selected.explanation}</p>

              {selected.similar_cases?.length > 0 && (
                <>
                  <p className="section-label">Similar past cases</p>
                  <ul className="similar-list">
                    {selected.similar_cases.map((c, i) => <li key={i}>{c}</li>)}
                  </ul>
                </>
              )}

              <p className="section-label">Raw transaction values</p>
              <div className="raw-grid">
                <span>Time: {selected.transaction.Time.toFixed(2)}</span>
                <span>Amount: {selected.transaction.Amount.toFixed(2)}</span>
                {Object.entries(selected.transaction)
                  .filter(([k]) => k.startsWith('V'))
                  .map(([k, v]) => (
                    <span key={k}>{k}: {v.toFixed(2)}</span>
                  ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;