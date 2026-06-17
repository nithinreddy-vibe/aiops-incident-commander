# ⚡ AIOps Incident Commander

[![CI/CD Pipeline](https://github.com/yourusername/aiops-incident-commander/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/yourusername/aiops-incident-commander/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**AIOps Incident Commander** is a comprehensive, open-source showcase project that demonstrates a modern DevOps and Site Reliability Engineering (SRE) stack enhanced by Artificial Intelligence. 

It simulates a realistic microservices environment, actively monitors it with Prometheus, uses machine learning (Isolation Forests) for anomaly detection, and leverages Large Language Models (LLMs) to automatically perform Root Cause Analysis (RCA) and remediation when chaos is injected.

This project is built to demonstrate end-to-end expertise in **Infrastructure as Code (IaC), Container Orchestration, Observability, and AI-driven Operations (AIOps).**

---

## 🏗️ Architecture

![Architecture Diagram](https://via.placeholder.com/800x400.png?text=AIOps+Architecture+Diagram) <!-- Replace with actual diagram if deployed -->

The system is composed of four main components running locally via Docker Compose (or deployable to EKS via Terraform/Helm):

1.  **Mock Microservices Generator (Python/Flask):** Simulates a 5-node service mesh (Frontend, API Gateway, Auth, Payment, Database). It exposes `/metrics` for Prometheus and a `/chaos` endpoint to artificially inject degradation (e.g., Memory Leaks, CPU Spikes, DB Latency).
2.  **Prometheus:** Scrapes telemetry data (CPU, memory, latency, error rates) from the services every 5 seconds.
3.  **AIOps Engine (Python/scikit-learn/LLM):** 
    *   Continuously polls Prometheus.
    *   Runs statistical anomaly detection (Z-scores / rolling thresholds).
    *   When an anomaly triggers, it fetches recent service logs and metrics.
    *   Constructs a prompt and queries an LLM (Gemini) to perform Root Cause Analysis. (Falls back to a smart local mock if no API key is provided).
    *   Executes auto-remediation playbooks to restore service health.
4.  **Interactive Dashboard (React/Vite):** A premium glassmorphism web UI to visualize system topology, real-time charts, live logs, the AI incident feed, and a "Chaos Control Center" to trigger failures.

---

## 🚀 Quick Start (Local Docker Sandbox)

You can run the entire AIOps platform locally using Docker.

### Prerequisites
*   Docker & Docker Compose (`docker compose` v2)
*   (Optional) Gemini API Key for real LLM analysis

### Running the Stack

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/yourusername/aiops-incident-commander.git
    cd aiops-incident-commander
    ```

2.  **(Optional) Add LLM Key:**
    Export your Gemini API key to enable live AI analysis. If omitted, the engine uses a smart mock fallback.
    ```bash
    export GEMINI_API_KEY="your_api_key_here"
    ```

3.  **Launch the environment:**
    ```bash
    docker compose up --build -d
    ```

4.  **Access the Dashboard:**
    Open your browser and navigate to **[http://localhost:3000](http://localhost:3000)**

---

## 🎮 The Showcase Workflow: Injecting Chaos

To see the AIOps engine in action, follow this workflow on the Dashboard:

1.  **Observe Normal State:** Notice all services are green and metrics are stable.
2.  **Inject Chaos:** Click a scenario in the "Chaos Control Center" (e.g., **Memory Leak** on the API Gateway).
3.  **Watch the Telemetry:** The memory chart will spike, and the API Gateway node will turn yellow, then red.
4.  **Anomaly Detection:** The AIOps Engine detects the threshold breach and creates an Incident.
5.  **AI Root Cause Analysis:** The engine reads the logs and metrics, queries the LLM, and populates the Incident feed with a detailed RCA (Root Cause, Impact, Evidence, and Remediation Steps).
6.  **Auto-Remediation:** Click "Auto-Remediate" on the incident. The engine executes a webhook that clears the chaos, restoring the system to a healthy state.

---

## 🛠️ Technology Stack

*   **Platform & Orchestration:** Docker, Docker Compose, Kubernetes (Helm), AWS EKS
*   **Infrastructure as Code:** Terraform
*   **Observability:** Prometheus
*   **Backend Services:** Python 3.11, Flask, NumPy, Scikit-learn
*   **Frontend Dashboard:** React 18, Vite, Recharts, CSS Glassmorphism
*   **CI/CD:** GitHub Actions (Linting, Trivy Security Scans, Docker Builds, Terraform Plan)
*   **AI Integration:** Google Generative AI (Gemini 1.5 Flash)

---

## 📂 Repository Structure

```
.
├── .github/workflows/       # CI/CD Pipelines (GitHub Actions)
├── infrastructure/
│   ├── kubernetes/          # Helm charts / K8s manifests
│   └── terraform/           # IaC for AWS EKS & Managed Prometheus
├── services/
│   ├── aiops/               # The AI Engine (Anomaly detection & LLM integration)
│   ├── dashboard/           # React/Vite Frontend
│   └── generator/           # Microservices & Chaos simulator
├── docker-compose.yml       # Local orchestration
├── prometheus.yml           # Observability config
└── README.md
```

---

## 👨‍💻 About

Designed to demonstrate production-ready DevOps practices combined with next-generation AI operations. This project illustrates how SRE teams can reduce Mean Time to Resolution (MTTR) by automating root cause analysis.
