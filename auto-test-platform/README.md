# Auto-Test Platform

A lightweight Python automation testing framework that supports parallel
test execution, configurable retry logic, HTML/JSON reporting, and a
centralised result-collection dashboard.

## Architecture

The platform is split into three layers so test execution, reporting, and
monitoring can evolve independently.

1. Test Execution Layer (`core/` + `main.py`)
- `BaseTest` defines the lifecycle (`setup -> execute -> teardown`) and outputs `TestResult`.
- `Runner` executes discovered tests in parallel and aggregates statuses.
- `retry` provides retry/backoff for flaky operations.
- `main.py` discovers tests, executes them, writes reports, and optionally posts to server.

2. Reporting Layer (`core/report.py` + `reports/`)
- `Reporter` converts runtime results into `report.html` and `report.json`.
- JSON output is CI/server-friendly; HTML is for local inspection.

3. Monitoring Layer (`server/app.py` + `core/station_simulator.py`)
- Flask server exposes:
    - `POST /results`: ingest test results from runner/CI.
    - `GET /api/results`: fetch collected test results.
    - `GET /api/stations`: fetch simulated station telemetry (default 10 stations).
    - `GET /`: dashboard view for both test results and station monitoring.
- `StationSimulator` keeps in-memory station state and updates status/metrics on each tick.

### Runtime Flow

1. `python main.py` discovers classes under `tests/` that inherit from `BaseTest`.
2. `Runner` runs tests concurrently and returns `TestResult` list.
3. `Reporter` generates HTML/JSON artifacts in `reports/`.
4. If `--server-url` is set, results are posted to `POST /results`.
5. Dashboard aggregates stored results and station telemetry for monitoring.

### Station Monitoring Flow (10 Stations)

1. Server startup initializes `StationSimulator(station_count=10)` by default.
2. On each dashboard/API request, station cache is refreshed at a fixed interval.
3. Each station record includes:
     `station_id`, `line`, `status`, `current_test`, `temperature_c`,
     `utilization_pct`, `pass_count`, `fail_count`, `last_heartbeat`.
4. Dashboard shows status counters (running/idle/warning/offline) and per-station table.

---

## Project Structure

```
auto-test-platform/
│
├── core/
│   ├── base_test.py   # Template Method Pattern — base class for all tests
│   ├── runner.py      # Parallel test runner (ThreadPool / ProcessPool)
│   ├── retry.py       # Retry decorator & policy with exponential back-off
│   ├── config.py      # YAML configuration loader
│   ├── report.py      # HTML + JSON report generator
│   └── station_simulator.py # Simulated station telemetry generator
│
├── tests/
│   ├── unit/          # Unit tests for each core module
│   ├── integration/   # Runner → Report pipeline tests
│   ├── e2e/           # Full end-to-end scenario tests
│   ├── unit/test_station_simulator.py
│   └── integration/test_station_monitoring_api.py
│
├── server/
│   └── app.py         # Flask dashboard + result-collection API
│
├── main.py            # CLI entry-point with test discovery
├── config.yaml        # Default configuration
├── requirements.txt
├── Dockerfile
└── .github/workflows/test.yml
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run all tests

```bash
cd auto-test-platform
python main.py
```

Reports are written to `reports/report.html` and `reports/report.json`.

### 3. Run with custom options

```bash
python main.py --workers 8 --timeout 60 --report-dir /tmp/reports
```

### 4. Start the dashboard server

```bash
python server/app.py
# Open http://localhost:5000
```

### 5. Run with pytest

```bash
pytest tests/ -v --tb=short
```

---

## Writing Tests

Subclass `BaseTest` and implement the `execute()` method:

```python
from core.base_test import BaseTest
from core.retry import retry

class MyTest(BaseTest):
    name = "my_test"

    def setup(self):
        # optional: prepare resources
        pass

    @retry(max_attempts=3, delay=0.2, exceptions=(IOError,))
    def execute(self):
        # your test logic here
        assert some_function() == expected_value

    def teardown(self):
        # optional: clean up resources
        pass

    def skip_condition(self) -> bool:
        # optional: return True to skip
        return False
```

---

## Configuration (`config.yaml`)

| Key | Default | Description |
|-----|---------|-------------|
| `runner.workers` | `4` | Parallel worker threads |
| `runner.timeout` | `120` | Per-test timeout (seconds) |
| `report.output_dir` | `reports` | Report output directory |
| `server.url` | `null` | Result server URL (optional) |
| `retry.max_attempts` | `3` | Default retry count |

---

## Docker

```bash
# Build
docker build -t auto-test-platform .

# Run tests
docker run --rm auto-test-platform

# Run the dashboard server
docker run -p 5000:5000 auto-test-platform python server/app.py
```

---

## CI / GitHub Actions

The workflow at `.github/workflows/test.yml` automatically runs the full
test suite on every push and pull request.
