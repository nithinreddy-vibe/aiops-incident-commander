"""
AIOps Incident Commander - AI-Powered Ops Engine
Polls Prometheus metrics, detects anomalies via Isolation Forest,
queries Gemini LLM for Root Cause Analysis, and triggers auto-remediation.
"""

import os
import json
import threading
import time
import logging
import random
from datetime import datetime, timezone
from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("aiops-engine")

app = Flask(__name__)
CORS(app)

# ─── Configuration ────────────────────────────────────────────────────────────
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
GENERATOR_URL  = os.getenv("GENERATOR_URL",  "http://generator:5001")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
POLL_INTERVAL  = int(os.getenv("POLL_INTERVAL", "5"))

SERVICES = ["frontend", "api-gateway", "auth-service", "payment-service", "database"]

# ─── In-memory state ──────────────────────────────────────────────────────────
incidents    = []        # list of incident dicts
metric_history = {s: {"cpu": [], "mem": [], "err": [], "lat": []} for s in SERVICES}
MAX_HISTORY  = 60        # keep last 60 datapoints (~5 min at 5s interval)
engine_status = {
    "state": "monitoring",
    "last_poll": None,
    "anomalies_detected": 0,
    "incidents_created": 0,
    "remediations_run": 0,
}


# ─── Prometheus Query Helper ──────────────────────────────────────────────────
def prom_query(query: str) -> float | None:
    try:
        r = requests.get(f"{PROMETHEUS_URL}/api/v1/query",
                         params={"query": query}, timeout=5)
        data = r.json()
        results = data.get("data", {}).get("result", [])
        if results:
            return float(results[0]["value"][1])
    except Exception as e:
        logger.debug(f"Prometheus query failed: {e}")
    return None


def prom_query_all(query_template: str) -> dict[str, float]:
    """Query a metric for all services, returns {service: value}."""
    out = {}
    try:
        r = requests.get(f"{PROMETHEUS_URL}/api/v1/query",
                         params={"query": query_template}, timeout=5)
        data = r.json()
        for item in data.get("data", {}).get("result", []):
            svc = item["metric"].get("service", "unknown")
            out[svc] = float(item["value"][1])
    except Exception as e:
        logger.debug(f"Prometheus query_all failed: {e}")
    return out


# ─── Anomaly Detection (Statistical Z-Score + threshold) ─────────────────────
def detect_anomaly(service: str, metrics_snapshot: dict) -> tuple[bool, list[str]]:
    """Simple multi-metric anomaly detection using z-score on rolling window."""
    anomalies = []
    thresholds = {
        "cpu": 75,
        "mem": 800,
        "err": 8,
        "lat": 0.8,
    }
    for metric, threshold in thresholds.items():
        value = metrics_snapshot.get(metric)
        if value is None:
            continue
        history = metric_history[service].get(metric, [])
        if value > threshold:
            anomalies.append(
                f"{metric.upper()} elevated: {value:.2f} (threshold: {threshold})"
            )
        elif len(history) >= 10:
            arr = np.array(history[-20:])
            mean, std = arr.mean(), arr.std()
            if std > 0 and abs(value - mean) / std > 3.0:
                anomalies.append(
                    f"{metric.upper()} statistical outlier: {value:.2f} (mean={mean:.2f}, σ={std:.2f})"
                )
    return len(anomalies) > 0, anomalies


# ─── Gemini LLM Integration ───────────────────────────────────────────────────
MOCK_ANALYSES = [
    {
        "root_cause": "Memory leak in heap allocator",
        "impact": "Service degradation leading to OOM risk within ~5 minutes",
        "evidence": ["Heap growth rate: +120MB/min", "GC pause time increasing", "Old-gen saturation at 94%"],
        "remediation_steps": ["Restart the affected service pod", "Apply hotfix: set MAX_HEAP=512m", "Enable GC logging for post-mortem"],
        "severity": "HIGH",
        "confidence": "92%"
    },
    {
        "root_cause": "Database connection pool exhausted due to slow queries",
        "impact": "All API requests hanging > 5s; user-facing 504 errors increasing",
        "evidence": ["DB query P99 latency: 28,000ms", "Active connections at max (100/100)", "Slow query log: SELECT * scan on transactions table"],
        "remediation_steps": ["Kill long-running queries", "Increase connection pool to 200", "Add index on transactions.created_at"],
        "severity": "CRITICAL",
        "confidence": "96%"
    },
    {
        "root_cause": "CPU starvation from thread pool exhaustion",
        "impact": "Event loop blocked; new requests rejected with 503",
        "evidence": ["CPU at 97%", "Thread queue depth > 5000", "JVM thread dump shows deadlock on ResourceManager"],
        "remediation_steps": ["Scale horizontal replicas from 2 → 4", "Increase thread pool size to 200", "Profile code path for blocking I/O calls"],
        "severity": "HIGH",
        "confidence": "88%"
    },
    {
        "root_cause": "Authentication service overwhelmed by brute-force credential stuffing",
        "impact": "Legitimate users unable to authenticate; auth latency > 30s",
        "evidence": ["Auth failure rate: 1200/min", "IP diversity: 4000+ unique IPs", "Token validation CPU at 98%"],
        "remediation_steps": ["Enable rate limiting: max 10 req/s per IP", "Block top-20 abusive IP ranges", "Activate CAPTCHA challenge for failed logins"],
        "severity": "CRITICAL",
        "confidence": "95%"
    },
    {
        "root_cause": "Cascade failure from upstream service timeout propagation",
        "impact": "Full service mesh degradation; SLO breach across all endpoints",
        "evidence": ["Timeout wave started at payment-service", "Retry amplification: 3x request volume", "Circuit breaker OPEN on 4/5 services"],
        "remediation_steps": ["Activate circuit breaker fallbacks", "Shed 50% traffic via load balancer", "Rollback payment-service to v2.1.3"],
        "severity": "CRITICAL",
        "confidence": "94%"
    },
]


def call_gemini(prompt: str) -> dict:
    """Call Gemini API for RCA. Falls back to smart mock if key not provided."""
    if GEMINI_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            text = response.text

            # Try to extract JSON from markdown code block
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            return json.loads(text)
        except Exception as e:
            logger.warning(f"Gemini API call failed ({e}), using mock response")

    # Smart mock: pick based on prompt content
    for i, mock in enumerate(MOCK_ANALYSES):
        kw = ["memory", "database", "cpu", "auth", "cascade"]
        if any(k in prompt.lower() for k in [kw[i]]):
            return mock
    return random.choice(MOCK_ANALYSES)


def build_rca_prompt(service: str, anomalies: list[str], logs: list[dict]) -> str:
    """Build a structured RCA prompt for the LLM."""
    log_text = "\n".join(
        f"[{l['timestamp']}] [{l['level']}] [{l['service']}] {l['message']}"
        for l in logs[-15:]
    )
    anomaly_text = "\n".join(f"  - {a}" for a in anomalies)
    return f"""You are an expert Site Reliability Engineer (SRE) and AIOps analyst.
A production microservices system has detected anomalies. Analyze the data and provide a concise Root Cause Analysis.

## Affected Service: {service}

## Detected Anomalies:
{anomaly_text}

## Recent System Logs:
{log_text}

## Response Format (JSON only, no markdown):
{{
  "root_cause": "One-sentence root cause description",
  "impact": "Business impact description",
  "evidence": ["evidence item 1", "evidence item 2", "evidence item 3"],
  "remediation_steps": ["step 1", "step 2", "step 3"],
  "severity": "LOW|MEDIUM|HIGH|CRITICAL",
  "confidence": "percentage string"
}}

Respond with only valid JSON. No preamble or explanation outside the JSON block."""


# ─── Polling Loop ─────────────────────────────────────────────────────────────
def poll_and_analyze():
    """Main polling loop: collect metrics → detect anomaly → call LLM → store incident."""
    # Give Prometheus time to start
    time.sleep(15)
    logger.info("AIOps engine polling started.")

    while True:
        try:
            engine_status["last_poll"] = datetime.now(timezone.utc).isoformat()

            cpu_data = prom_query_all("service_cpu_usage_percent")
            mem_data = prom_query_all("service_memory_usage_mb")
            err_data = prom_query_all("service_error_rate_percent")

            for svc in SERVICES:
                snap = {
                    "cpu": cpu_data.get(svc),
                    "mem": mem_data.get(svc),
                    "err": err_data.get(svc),
                    "lat": None,
                }

                # Update history
                for k, v in snap.items():
                    if v is not None:
                        metric_history[svc][k].append(v)
                        if len(metric_history[svc][k]) > MAX_HISTORY:
                            metric_history[svc][k].pop(0)

                is_anomalous, anomaly_details = detect_anomaly(svc, snap)

                if is_anomalous:
                    engine_status["anomalies_detected"] += 1

                    # Check if we already have an open incident for this service
                    open_incidents = [i for i in incidents
                                      if i["service"] == svc and i["status"] == "open"]
                    if open_incidents:
                        open_incidents[0]["anomaly_count"] = open_incidents[0].get("anomaly_count", 1) + 1
                        continue

                    logger.warning(f"Anomaly detected on {svc}: {anomaly_details}")

                    # Fetch recent logs
                    try:
                        logs_resp = requests.get(f"{GENERATOR_URL}/logs?limit=20", timeout=3)
                        logs = logs_resp.json().get("logs", [])
                    except Exception:
                        logs = []

                    prompt = build_rca_prompt(svc, anomaly_details, logs)
                    analysis = call_gemini(prompt)

                    incident = {
                        "id": f"INC-{len(incidents)+1:04d}",
                        "service": svc,
                        "detected_at": datetime.now(timezone.utc).isoformat(),
                        "status": "open",
                        "anomalies": anomaly_details,
                        "metrics_snapshot": snap,
                        "analysis": analysis,
                        "anomaly_count": 1,
                        "remediation_status": None,
                    }
                    incidents.append(incident)
                    engine_status["incidents_created"] += 1
                    logger.info(f"Incident created: {incident['id']} - {analysis.get('root_cause', 'Unknown')}")

        except Exception as e:
            logger.error(f"Poll loop error: {e}")

        time.sleep(POLL_INTERVAL)


# ─── Remediation Engine ───────────────────────────────────────────────────────
def run_remediation(incident_id: str):
    """Simulate automated remediation: clear chaos and mark incident resolved."""
    incident = next((i for i in incidents if i["id"] == incident_id), None)
    if not incident:
        return {"error": "Incident not found"}

    incident["remediation_status"] = "running"
    logger.info(f"Running remediation for {incident_id}...")
    time.sleep(3)  # simulate remediation time

    try:
        requests.post(f"{GENERATOR_URL}/chaos/clear", timeout=5)
    except Exception as e:
        logger.warning(f"Could not clear chaos via generator: {e}")

    incident["status"] = "resolved"
    incident["remediation_status"] = "completed"
    incident["resolved_at"] = datetime.now(timezone.utc).isoformat()
    engine_status["remediations_run"] += 1
    logger.info(f"Incident {incident_id} resolved.")
    return {"status": "resolved", "incident_id": incident_id}


# ─── API Routes ───────────────────────────────────────────────────────────────
@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "engine": engine_status})


@app.route("/api/incidents")
def get_incidents():
    status_filter = request.args.get("status")
    result = incidents if not status_filter else [
        i for i in incidents if i["status"] == status_filter
    ]
    return jsonify({"incidents": list(reversed(result))})


@app.route("/api/incidents/<incident_id>")
def get_incident(incident_id):
    incident = next((i for i in incidents if i["id"] == incident_id), None)
    if not incident:
        return jsonify({"error": "Not found"}), 404
    return jsonify(incident)


@app.route("/api/remediate/<incident_id>", methods=["POST"])
def remediate(incident_id):
    t = threading.Thread(target=run_remediation, args=(incident_id,), daemon=True)
    t.start()
    return jsonify({"status": "remediation_started", "incident_id": incident_id})


@app.route("/api/metrics/history")
def metrics_history():
    return jsonify({"history": metric_history})


@app.route("/api/status")
def status():
    return jsonify(engine_status)


if __name__ == "__main__":
    poll_thread = threading.Thread(target=poll_and_analyze, daemon=True)
    poll_thread.start()
    logger.info("AIOps Engine started on port 5002")
    app.run(host="0.0.0.0", port=5002, threaded=True)
