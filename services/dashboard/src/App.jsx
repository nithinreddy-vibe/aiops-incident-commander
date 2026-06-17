import { useState, useEffect, useRef, useCallback } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend, AreaChart, Area
} from 'recharts'

// ─── API Configuration ────────────────────────────────────────────────────────
const AIOPS_API   = import.meta.env.VITE_AIOPS_URL   || 'http://localhost:5002'
const GEN_API     = import.meta.env.VITE_GEN_URL     || 'http://localhost:5001'

const apiFetch = async (url, options = {}) => {
  const resp = await fetch(url, options)
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return resp.json()
}

// ─── Service Definitions ──────────────────────────────────────────────────────
const SERVICES = [
  { id: 'frontend',        label: 'Frontend',       emoji: '🌐' },
  { id: 'api-gateway',     label: 'API Gateway',    emoji: '🔀' },
  { id: 'auth-service',    label: 'Auth Service',   emoji: '🔐' },
  { id: 'payment-service', label: 'Payment',        emoji: '💳' },
  { id: 'database',        label: 'Database',       emoji: '🗄️' },
]

const CHAOS_SCENARIOS = [
  { id: 'memory_leak',     label: 'Memory Leak',    emoji: '💾', desc: 'Heap grows unbounded', cls: 'memory', target: 'api-gateway' },
  { id: 'cpu_spike',       label: 'CPU Spike',      emoji: '🔥', desc: 'Thread pool exhausted', cls: 'cpu', target: 'frontend' },
  { id: 'db_latency',      label: 'DB Latency',     emoji: '🐌', desc: 'Slow query timeout', cls: 'db', target: 'database' },
  { id: 'cascade_failure', label: 'Cascade Failure',emoji: '💥', desc: 'System-wide failure', cls: 'cascade', target: 'all' },
  { id: 'auth_storm',      label: 'Auth Storm',     emoji: '🌪️', desc: 'Credential stuffing', cls: 'auth', target: 'auth-service' },
]

const CHART_COLORS = ['#00d4ff', '#00ff88', '#9b6dff', '#ffd700', '#ff6b35']

// ─── Custom Tooltip ───────────────────────────────────────────────────────────
const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: 'rgba(10,25,50,0.95)', border: '1px solid rgba(0,212,255,0.2)',
      borderRadius: 8, padding: '10px 14px', fontSize: '0.72rem', fontFamily: 'JetBrains Mono, monospace'
    }}>
      <div style={{ color: '#8babd4', marginBottom: 6 }}>{label}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color, display: 'flex', justifyContent: 'space-between', gap: 16 }}>
          <span>{p.name}</span>
          <span style={{ fontWeight: 700 }}>{typeof p.value === 'number' ? p.value.toFixed(1) : p.value}</span>
        </div>
      ))}
    </div>
  )
}

// ─── Main App ─────────────────────────────────────────────────────────────────
export default function App() {
  const [incidents, setIncidents]         = useState([])
  const [serviceHealth, setServiceHealth] = useState({})
  const [logs, setLogs]                   = useState([])
  const [engineStatus, setEngineStatus]   = useState(null)
  const [chaosState, setChaosState]       = useState({ active: false, type: null })
  const [chartData, setChartData]         = useState([])
  const [remediating, setRemediating]     = useState({})
  const [lastUpdate, setLastUpdate]       = useState(null)
  const logEndRef = useRef(null)

  // ─── Data Fetching ─────────────────────────────────────────────────────────
  const fetchAll = useCallback(async () => {
    try {
      const [incData, healthData, logData, engData] = await Promise.allSettled([
        apiFetch(`${AIOPS_API}/api/incidents`),
        apiFetch(`${GEN_API}/status`),
        apiFetch(`${GEN_API}/logs?limit=60`),
        apiFetch(`${AIOPS_API}/api/status`),
      ])

      if (incData.status === 'fulfilled')  setIncidents(incData.value.incidents || [])
      if (healthData.status === 'fulfilled') {
        setServiceHealth(healthData.value.services || {})
        setChaosState(healthData.value.chaos || { active: false })
      }
      if (logData.status === 'fulfilled')  setLogs(logData.value.logs || [])
      if (engData.status === 'fulfilled')  setEngineStatus(engData.value)

      setLastUpdate(new Date().toLocaleTimeString())
    } catch (e) {
      console.warn('Fetch error:', e)
    }
  }, [])

  // Build chart data from history endpoint
  const fetchHistory = useCallback(async () => {
    try {
      const data = await apiFetch(`${AIOPS_API}/api/metrics/history`)
      const history = data.history || {}
      const len = Math.max(...Object.values(history).map(s => s.cpu?.length || 0), 0)
      if (len === 0) return

      const points = []
      for (let i = Math.max(0, len - 30); i < len; i++) {
        const pt = { t: i }
        SERVICES.forEach(({ id }) => {
          if (history[id]) {
            pt[`${id}_cpu`] = history[id].cpu?.[i] ?? null
            pt[`${id}_mem`] = history[id].mem?.[i] ?? null
          }
        })
        points.push(pt)
      }
      setChartData(points)
    } catch (e) { /* ignore */ }
  }, [])

  useEffect(() => {
    fetchAll()
    fetchHistory()
    const t1 = setInterval(fetchAll, 3000)
    const t2 = setInterval(fetchHistory, 5000)
    return () => { clearInterval(t1); clearInterval(t2) }
  }, [fetchAll, fetchHistory])

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs.length])

  // ─── Chaos Actions ─────────────────────────────────────────────────────────
  const injectChaos = async (scenario) => {
    try {
      await apiFetch(`${GEN_API}/chaos`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: scenario.id, target: scenario.target })
      })
    } catch (e) { console.error('Chaos inject failed:', e) }
  }

  const clearChaos = async () => {
    try {
      await apiFetch(`${GEN_API}/chaos/clear`, { method: 'POST' })
    } catch (e) { console.error('Chaos clear failed:', e) }
  }

  // ─── Remediation ───────────────────────────────────────────────────────────
  const remediate = async (incidentId) => {
    setRemediating(r => ({ ...r, [incidentId]: true }))
    try {
      await apiFetch(`${AIOPS_API}/api/remediate/${incidentId}`, { method: 'POST' })
      setTimeout(() => {
        setRemediating(r => ({ ...r, [incidentId]: false }))
        fetchAll()
      }, 4000)
    } catch (e) {
      setRemediating(r => ({ ...r, [incidentId]: false }))
    }
  }

  // ─── Derived State ─────────────────────────────────────────────────────────
  const openIncidents     = incidents.filter(i => i.status === 'open')
  const resolvedIncidents = incidents.filter(i => i.status === 'resolved')
  const criticalCount     = openIncidents.filter(i => i.analysis?.severity === 'CRITICAL').length
  const overallHealth     = criticalCount > 0 ? 'critical'
    : openIncidents.length > 0 ? 'warning' : 'healthy'

  return (
    <div className="app-wrapper">
      {/* ─── Header ─────────────────────────────────────────────────────────── */}
      <header className="header">
        <div className="header-brand">
          <div className="header-logo">⚡</div>
          <div>
            <div className="header-title">AIOps Incident Commander</div>
            <div className="header-subtitle">AI-POWERED SITE RELIABILITY ENGINEERING PLATFORM</div>
          </div>
        </div>

        <div className="header-meta">
          <div className="engine-status-badge">
            <div className={`status-dot ${overallHealth}`} />
            <span style={{ color: overallHealth === 'critical' ? 'var(--accent-red)' : overallHealth === 'warning' ? 'var(--accent-yellow)' : 'var(--accent-green)' }}>
              {overallHealth === 'critical' ? '⚠ INCIDENT ACTIVE' : overallHealth === 'warning' ? '⚡ DEGRADED' : '✓ ALL SYSTEMS GO'}
            </span>
          </div>
          {engineStatus && (
            <div className="engine-status-badge">
              <div className="status-dot active" />
              <span>AIOps Engine</span>
            </div>
          )}
          {lastUpdate && (
            <div className="last-poll-time">Updated {lastUpdate}</div>
          )}
        </div>
      </header>

      {/* ─── Main Content ────────────────────────────────────────────────────── */}
      <main className="main-content">

        {/* ── KPI Row ──────────────────────────────────────────────────────── */}
        <div className="dashboard-grid" style={{ marginBottom: 20 }}>
          <div className="card">
            <div className="card-header">
              <span className="card-title">Open Incidents</span>
              <span className="card-icon">🚨</span>
            </div>
            <div className={`kpi-value ${openIncidents.length > 0 ? 'red' : 'green'}`}>
              {openIncidents.length}
            </div>
            <div className="kpi-label">Requiring Attention</div>
          </div>

          <div className="card">
            <div className="card-header">
              <span className="card-title">Anomalies Detected</span>
              <span className="card-icon">🔍</span>
            </div>
            <div className="kpi-value cyan">
              {engineStatus?.anomalies_detected ?? '—'}
            </div>
            <div className="kpi-label">Total this session</div>
          </div>

          <div className="card">
            <div className="card-header">
              <span className="card-title">Auto-Remediated</span>
              <span className="card-icon">🤖</span>
            </div>
            <div className="kpi-value green">
              {engineStatus?.remediations_run ?? 0}
            </div>
            <div className="kpi-label">Incidents auto-resolved</div>
          </div>

          <div className="card">
            <div className="card-header">
              <span className="card-title">Services Healthy</span>
              <span className="card-icon">💚</span>
            </div>
            <div className="kpi-value purple">
              {Object.values(serviceHealth).filter(v => v === 'healthy').length}
              <span style={{ fontSize: '1.2rem', color: 'var(--text-muted)' }}>/{SERVICES.length}</span>
            </div>
            <div className="kpi-label">Nominal services</div>
          </div>
        </div>

        {/* ── Topology + Metrics ───────────────────────────────────────────── */}
        <div className="dashboard-grid-main">

          {/* Service Topology */}
          <div className="card">
            <div className="card-header">
              <span className="card-title">Service Topology</span>
              <span className="card-icon">🕸️</span>
            </div>
            <div className="topology-grid">
              {SERVICES.map(svc => {
                const h = serviceHealth[svc.id] || 'healthy'
                return (
                  <div key={svc.id} className={`service-node ${h}`}>
                    <div className="service-node-icon">{svc.emoji}</div>
                    <div className="service-node-name">{svc.label}</div>
                    <div className={`service-node-status ${h}`}>{h.toUpperCase()}</div>
                  </div>
                )
              })}
            </div>

            {chaosState?.active && (
              <div className="chaos-active-banner" style={{ marginTop: 16 }}>
                ⚡ CHAOS ACTIVE: {chaosState.type?.replace('_', ' ').toUpperCase()} — {chaosState.description}
              </div>
            )}
          </div>

          {/* CPU Chart */}
          <div className="card">
            <div className="card-header">
              <span className="card-title">CPU Usage (%) — Live</span>
              <span className="card-icon">📊</span>
            </div>
            <div className="chart-legend">
              {SERVICES.map((s, i) => (
                <div className="chart-legend-item" key={s.id}>
                  <div className="legend-dot" style={{ background: CHART_COLORS[i] }} />
                  {s.label}
                </div>
              ))}
            </div>
            <div className="chart-container">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData}>
                  <defs>
                    {SERVICES.map((s, i) => (
                      <linearGradient key={s.id} id={`grad-cpu-${i}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={CHART_COLORS[i]} stopOpacity={0.2} />
                        <stop offset="95%" stopColor={CHART_COLORS[i]} stopOpacity={0} />
                      </linearGradient>
                    ))}
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="t" tick={{ fill: '#4a6080', fontSize: 10 }} tickLine={false} />
                  <YAxis domain={[0, 100]} tick={{ fill: '#4a6080', fontSize: 10 }} tickLine={false} width={30} />
                  <Tooltip content={<CustomTooltip />} />
                  {SERVICES.map((s, i) => (
                    <Area key={s.id} type="monotone" dataKey={`${s.id}_cpu`}
                      name={s.label} stroke={CHART_COLORS[i]} strokeWidth={1.5}
                      fill={`url(#grad-cpu-${i})`} dot={false} />
                  ))}
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Chaos Control Panel */}
          <div className="card chaos-panel">
            <div className="card-header">
              <span className="card-title">Chaos Control Center</span>
              <span className="card-icon">💀</span>
            </div>
            <div className="chaos-grid">
              {CHAOS_SCENARIOS.map(s => (
                <button key={s.id} className={`chaos-btn ${s.cls}`}
                  onClick={() => injectChaos(s)}
                  id={`chaos-btn-${s.id}`}
                  aria-label={`Inject ${s.label} chaos`}>
                  <span className="chaos-btn-emoji">{s.emoji}</span>
                  <span className="chaos-btn-title">{s.label}</span>
                  <span className="chaos-btn-desc">{s.desc}</span>
                </button>
              ))}
            </div>
            <button className="chaos-clear-btn" id="chaos-clear-btn" onClick={clearChaos}>
              ✓ Clear All Chaos — Restore System
            </button>
            {chaosState?.active && (
              <div className="chaos-active-banner">
                🔴 {chaosState.description || 'Chaos scenario active'}
              </div>
            )}
          </div>
        </div>

        {/* ── Incidents + Logs ─────────────────────────────────────────────── */}
        <div className="dashboard-grid-bottom">

          {/* Incidents Panel */}
          <div className="card">
            <div className="card-header">
              <span className="card-title">AI Incident Commander</span>
              <span className="card-icon">🧠</span>
            </div>

            {incidents.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">✅</div>
                <div className="empty-state-text">No incidents detected. System operating nominally.<br />Try injecting chaos to trigger the AIOps engine!</div>
              </div>
            ) : (
              <div className="incidents-list">
                {incidents.map(inc => (
                  <div key={inc.id} className={`incident-item ${inc.status}`}>
                    <div className="incident-header">
                      <span className="incident-id">{inc.id}</span>
                      <span className={`incident-severity-badge severity-${inc.analysis?.severity || 'MEDIUM'}`}>
                        {inc.analysis?.severity || 'MEDIUM'}
                      </span>
                    </div>

                    <div className="incident-service">
                      {SERVICES.find(s => s.id === inc.service)?.emoji} {inc.service}
                    </div>

                    {inc.analysis?.root_cause && (
                      <div className="incident-rca">
                        <strong style={{ color: 'var(--accent-cyan)', fontSize: '0.68rem' }}>ROOT CAUSE: </strong>
                        {inc.analysis.root_cause}
                      </div>
                    )}

                    {inc.analysis?.evidence && (
                      <ul className="evidence-list" style={{ marginBottom: 8 }}>
                        {inc.analysis.evidence.slice(0, 2).map((e, i) => (
                          <li key={i}>{e}</li>
                        ))}
                      </ul>
                    )}

                    {inc.analysis?.remediation_steps && inc.status === 'open' && (
                      <ul className="steps-list" style={{ marginBottom: 10 }}>
                        {inc.analysis.remediation_steps.slice(0, 2).map((s, i) => (
                          <li key={i}>{s}</li>
                        ))}
                      </ul>
                    )}

                    <div className="incident-meta">
                      <span className="incident-time">
                        {new Date(inc.detected_at).toLocaleTimeString()}
                        {inc.analysis?.confidence && ` · AI Confidence: ${inc.analysis.confidence}`}
                      </span>
                      {inc.status === 'open' ? (
                        <button
                          className="remediate-btn"
                          id={`remediate-btn-${inc.id}`}
                          disabled={remediating[inc.id]}
                          onClick={() => remediate(inc.id)}
                        >
                          {remediating[inc.id] ? '⏳ Remediating…' : '🤖 Auto-Remediate'}
                        </button>
                      ) : (
                        <span className="resolved-badge">✓ RESOLVED {inc.resolved_at ? new Date(inc.resolved_at).toLocaleTimeString() : ''}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Log Stream */}
          <div className="card">
            <div className="card-header">
              <span className="card-title">Live Log Stream</span>
              <span className="card-icon">📋</span>
            </div>
            <div className="log-stream">
              {logs.length === 0 ? (
                <div className="empty-state" style={{ padding: 20 }}>
                  <div className="empty-state-icon" style={{ fontSize: '1.5rem' }}>📭</div>
                  <div className="empty-state-text">Waiting for logs…</div>
                </div>
              ) : (
                logs.map((log, i) => (
                  <div key={i} className="log-line">
                    <span className="log-time">{log.timestamp?.split('T')[1]?.replace('Z','') || ''}</span>
                    <span className={`log-level ${log.level}`}>{log.level}</span>
                    <span className="log-service">[{log.service}]</span>
                    <span className="log-msg">{log.message}</span>
                  </div>
                ))
              )}
              <div ref={logEndRef} />
            </div>

            {/* Memory Usage Chart */}
            <div style={{ marginTop: 16 }}>
              <div className="section-title">Memory Usage (MB) — Live</div>
              <div style={{ height: 120 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                    <XAxis dataKey="t" tick={{ fill: '#4a6080', fontSize: 9 }} tickLine={false} hide />
                    <YAxis tick={{ fill: '#4a6080', fontSize: 9 }} tickLine={false} width={40} />
                    <Tooltip content={<CustomTooltip />} />
                    {SERVICES.map((s, i) => (
                      <Line key={s.id} type="monotone" dataKey={`${s.id}_mem`}
                        name={s.label} stroke={CHART_COLORS[i]} strokeWidth={1.5}
                        dot={false} />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </div>

      </main>
    </div>
  )
}
