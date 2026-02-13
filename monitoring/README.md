# Monitoring Stack

This folder contains Prometheus and Grafana for monitoring your services.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                          Your Network                        │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────┐         ┌──────────────────┐           │
│  │ Inference Server │         │   gRPC Client    │           │
│  │  (Port 50051)    │         │  (Port 50051)    │           │
│  │                  │◄────────│  consumes        │           │
│  └──────────────────┘         └──────────────────┘           │
│           ▲                                                   │
│           │ (metrics on port 8000 - optional)               │
│           │                                                   │
│  ┌────────┴──────────────────────────────────────┐          │
│  │        Monitoring Stack (in /monitoring)      │          │
│  ├─────────────────────────────────────────────────┤         │
│  │                                                │          │
│  │  ┌─────────────────┐    ┌──────────────────┐ │          │
│  │  │  Prometheus     │    │     Grafana      │ │          │
│  │  │  (Port 9090)    ├───►│   (Port 3000)    │ │          │
│  │  │  - Scrapes      │    │   - Visualizes   │ │          │
│  │  │  - Stores       │    │   - Dashboards   │ │          │
│  │  │                 │    │   - Alerts       │ │          │
│  │  └─────────────────┘    └──────────────────┘ │          │
│  │                                                │          │
│  └────────────────────────────────────────────────┘          │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Ports

| Service | Port | Purpose |
|---------|------|---------|
| Prometheus | 9090 | Metrics database & API |
| Node Exporter | 9100 | Host OS metrics (CPU, RAM, disk, network) |
| cAdvisor | 8080 | Container metrics (per-container CPU, memory, I/O) |
| Grafana | 3000 | Dashboards & visualization |
| Inference Server | 50051 | gRPC API (optional metrics on 8000) |
| gRPC Client | 50051 | connects to inference server |

## Quick Start

```bash
cd monitoring
docker-compose up -d
```

Then access:
- **Grafana**: http://localhost:3000 (admin/admin)
- **Prometheus**: http://localhost:9090

## How It Works

1. **Node Exporter** exposes host OS metrics (CPU, memory, disk, network)
2. **cAdvisor** exposes container-level metrics (per-container resource usage)
3. **Prometheus** scrapes metrics from Node Exporter, cAdvisor, and your services
4. **Grafana** queries Prometheus and displays dashboards

## Available Metrics

**Host metrics (Node Exporter):**
- CPU usage, load average
- Memory (total, used, available, free)
- Disk space and I/O
- Network traffic (RX/TX)

**Container metrics (cAdvisor):**
- Per-container CPU usage
- Per-container memory (RSS, cache, swap)
- Container network I/O
- Container disk I/O

**Application metrics (optional):**
- Your custom metrics from inference-server and grpc-client (when instrumented)

## Querying Metrics

Common queries in Grafana:

**CPU usage:**
```
rate(node_cpu_seconds_total{mode="system"}[5m]) * 100
```

**Memory usage:**
```
(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100
```

**Container memory:**
```
container_memory_usage_bytes{name="inference-server"}
```

**Container CPU:**
```
rate(container_cpu_usage_seconds_total{name="grpc-client"}[5m])
```

## Adding Custom Application Metrics

To instrument your inference server or client:

1. Install prometheus client: `pip install prometheus-client`
2. Export metrics on port 8000
3. Uncomment the job in `prometheus.yml`
4. Restart docker-compose

See commented jobs in `prometheus.yml` for exact endpoints.

## Stop

```bash
docker-compose down
```
