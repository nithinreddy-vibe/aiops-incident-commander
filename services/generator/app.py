"""
AIOps Incident Commander - Mock Microservices Generator
Simulates a realistic microservices cluster with Prometheus metrics.
Supports chaos injection via /chaos endpoint.
"""

import threading
import time
import random
import logging
import math
from flask import Flask, jsonify, request
from flask_cors import CORS
from prometheus_client import (
    Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
logger = logging.getLogger("generator")

app = Flask(__name__)
CORS(app)

# ─── Prometheus Metrics ───────────────────────────────────────────────────────
cpu_usage = Gauge("service_cpu_usage_percent", "CPU usage percent", ["service"])
memory_usage = Gauge("service_memory_usage_mb", "Memory usage in MB", ["service"])
request_latency = Histogram(
    "service_request_latency_seconds",
    "Request latency in seconds",
    ["service", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)
request_count = Counter("service_requests_total", "Total requests", ["service", "status"])
error_rate = Gauge("service_error_rate_percent", "Error rate percent", ["service"])
db_connections = Gauge("db_active_connections", "Active database connections", ["db"])
db_latency = Gauge("db_query_latency_ms", "DB query latency in ms", ["db"])
auth_failures = Counter("auth_failures_total", "Authentication failure count", ["service"])

# ─── Services Definition ─────────────────────────────────────────────────────
SERVICES = ["frontend", "api-gateway", "auth-service", "payment-service", "database"]

BASELINE = {
    "frontend":       {"cpu": 20, "mem": 256, "latency": 0.05, "error": 0.5},
    "api-gateway":    {"cpu": 30, "mem": 512, "latency": 0.08, "error": 0.3},
    "auth-service":   {"cpu": 15, "mem": 128, "latency": 0.03, "error": 0.2},
    "payment-service":{"cpu": 25, "mem": 384, "latency": 0.12, "error": 0.4},
    "database":       {"cpu": 40, "mem": 1024, "latency": 0.02, "error": 0.1},
}

# Active chaos state
chaos_state = {
    "active": False,
    "type": None,
    "target": None,
    "started_at": None,
    "description": ""
}

# System health state
service_health = {svc: "healthy" for svc in SERVICES}

# Logs accumulator
system_logs = []
MAX_LOGS = 200


def add_log(level, service, message):
    """Append a structured log entry."""
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "level": level,
        "service": service,
        "message": message
    }
    system_logs.append(entry)
    if len(system_logs) > MAX_LOGS:
        system_logs.pop(0)


def get_noisy(base, noise_factor=0.08):
    """Add realistic Gaussian noise to a metric."""
    return max(0, base + base * random.gauss(0, noise_factor))


def simulate_metrics():
    """Background thread: continuously update Prometheus metrics based on chaos state."""
    t = 0
    while True:
        t += 1
        for svc in SERVICES:
            bl = BASELINE[svc]
            cpu_mult = 1.0
            mem_mult = 1.0
            lat_mult = 1.0
            err_mult = 1.0

            # Apply chaos modifiers
            if chaos_state["active"]:
                target = chaos_state["target"]
                ctype = chaos_state["type"]
                if target == svc or target == "all":
                    if ctype == "memory_leak":
                        elapsed = time.time() - chaos_state["started_at"]
                        mem_mult = 1.0 + (elapsed / 30.0)  # grows over 30 seconds
                        cpu_mult = 1.2
                    elif ctype == "cpu_spike":
                        cpu_mult = 4.5 + random.uniform(-0.5, 0.5)
                        lat_mult = 2.0
                    elif ctype == "db_latency":
                        lat_mult = 15.0 + random.uniform(-2, 2)
                        err_mult = 5.0
                    elif ctype == "cascade_failure":
                        cpu_mult = 3.0
                        mem_mult = 2.0
                        lat_mult = 10.0
                        err_mult = 20.0
                    elif ctype == "auth_storm":
                        if svc == "auth-service":
                            cpu_mult = 5.0
                            err_mult = 50.0
                        lat_mult = 3.0

            c_cpu = get_noisy(bl["cpu"] * cpu_mult)
            c_mem = get_noisy(bl["mem"] * mem_mult)
            c_lat = get_noisy(bl["latency"] * lat_mult)
            c_err = get_noisy(bl["error"] * err_mult)

            cpu_usage.labels(service=svc).set(min(c_cpu, 100))
            memory_usage.labels(service=svc).set(c_mem)
            error_rate.labels(service=svc).set(min(c_err, 100))

            # Histogram observation
            request_latency.labels(service=svc, endpoint="/api").observe(c_lat)

            # Request counters
            if random.random() < 0.95:
                request_count.labels(service=svc, status="200").inc()
            else:
                request_count.labels(service=svc, status="500").inc()

            # DB metrics
            if svc == "database":
                db_latency.labels(db="primary").set(get_noisy(5 * lat_mult))
                db_connections.labels(db="primary").set(
                    get_noisy(20 * (mem_mult if chaos_state.get("type") == "memory_leak" else 1))
                )

            # Update health state
            if c_cpu > 80 or c_err > 10 or c_lat > 1.0:
                service_health[svc] = "critical" if (c_cpu > 90 or c_err > 25) else "warning"
            else:
                service_health[svc] = "healthy"

        # Generate realistic log traffic
        if t % 5 == 0:
            svc = random.choice(SERVICES)
            if chaos_state["active"]:
                msgs = {
                    "memory_leak": f"WARNING: Heap size growing - current {random.randint(400, 2000)}MB. GC not keeping up.",
                    "cpu_spike":   f"ERROR: Thread pool exhausted. CPU at {random.randint(85, 99)}%. Requests queuing.",
                    "db_latency":  f"ERROR: DB query timeout after {random.randint(5000, 30000)}ms on SELECT * FROM transactions",
                    "cascade_failure": f"CRITICAL: Circuit breaker OPEN on {svc}. Downstream calls failing.",
                    "auth_storm":  f"ERROR: Auth token validation failed - rate: {random.randint(200, 1000)} req/s",
                }
                level = "ERROR"
                msg = msgs.get(chaos_state["type"], "ERROR: Unknown service degradation detected.")
                add_log(level, svc, msg)
                auth_failures.labels(service=svc).inc(random.randint(1, 10) if chaos_state["type"] == "auth_storm" else 0)
            else:
                add_log("INFO", random.choice(SERVICES), random.choice([
                    "Health check passed. All systems nominal.",
                    "Request processed successfully in 45ms.",
                    "Cache hit ratio: 94.2%. Serving from cache.",
                    "Scheduled maintenance task completed.",
                    "Metrics exported to Prometheus.",
                ]))

        time.sleep(2)


# ─── API Routes ───────────────────────────────────────────────────────────────
@app.route("/metrics")
def metrics():
    """Prometheus scrape endpoint."""
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


@app.route("/health")
def health():
    return jsonify({"status": "ok", "services": service_health})


@app.route("/chaos", methods=["POST"])
def inject_chaos():
    """Inject a chaos scenario."""
    data = request.get_json(force=True)
    chaos_type = data.get("type", "cpu_spike")
    target = data.get("target", "all")

    descriptions = {
        "memory_leak":     f"Memory leak injected into {target}. Heap growing unbounded.",
        "cpu_spike":       f"CPU spike injected into {target}. Thread pool exhausting.",
        "db_latency":      f"Database query slowness injected. Transactions timing out.",
        "cascade_failure": f"Cascade failure triggered across all services.",
        "auth_storm":      f"Authentication storm injected. Auth service overwhelmed.",
    }

    chaos_state["active"] = True
    chaos_state["type"] = chaos_type
    chaos_state["target"] = target
    chaos_state["started_at"] = time.time()
    chaos_state["description"] = descriptions.get(chaos_type, "Unknown chaos type")

    add_log("CRITICAL", "chaos-engine", f"CHAOS INJECTED: {chaos_type} on {target}")
    logger.warning(f"Chaos injected: type={chaos_type}, target={target}")
    return jsonify({"status": "chaos_active", "type": chaos_type, "target": target,
                    "description": chaos_state["description"]})


@app.route("/chaos/clear", methods=["POST"])
def clear_chaos():
    """Clear active chaos and restore normal operation."""
    chaos_state["active"] = False
    chaos_state["type"] = None
    chaos_state["target"] = None
    chaos_state["started_at"] = None
    chaos_state["description"] = ""
    add_log("INFO", "chaos-engine", "Chaos cleared. All services restored to baseline.")
    logger.info("Chaos cleared. System restored.")
    return jsonify({"status": "normal", "message": "All chaos cleared. System restored."})


@app.route("/status")
def status():
    """Full system status."""
    return jsonify({
        "services": service_health,
        "chaos": chaos_state,
        "log_count": len(system_logs)
    })


@app.route("/logs")
def get_logs():
    """Return recent system logs."""
    limit = int(request.args.get("limit", 50))
    return jsonify({"logs": system_logs[-limit:]})


if __name__ == "__main__":
    sim_thread = threading.Thread(target=simulate_metrics, daemon=True)
    sim_thread.start()
    logger.info("Mock microservices generator started on port 5001")
    app.run(host="0.0.0.0", port=5001, threaded=True)
