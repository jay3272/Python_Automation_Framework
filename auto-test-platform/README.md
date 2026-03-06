# Auto-Test Platform

一個輕量的 Python 自動化測試框架，支援平行測試執行、可設定重試策略、
HTML/JSON 報表，以及集中式測試結果儀表板。

技術文件：`TECHNICAL_DOCUMENTATION.md`

## 架構總覽

平台分成三層，讓測試執行、報表輸出、監控展示可以各自演進。

1. 測試執行層（`core/` + `main.py`）
- `BaseTest` 定義測試生命週期（`setup -> execute -> teardown`）並輸出 `TestResult`。
- `Runner` 平行執行測試並彙整結果。
- `retry` 提供 flaky 操作的重試與退避（backoff）。
- `main.py` 負責測試探索、執行、產出報表，並可選擇上拋結果到伺服器。

2. 報表層（`core/report.py` + `reports/`）
- `Reporter` 將執行結果輸出成 `report.html` 與 `report.json`。
- JSON 適合 CI 與系統串接，HTML 適合人工檢視。

3. 監控層（`server/app.py` + `core/station_simulator.py`）
- Flask 服務提供：
  - `POST /results`：接收 runner/CI 上拋的測試結果。
  - `GET /api/results`：回傳收集到的測試結果。
  - `GET /api/stations`：回傳測試站遙測資料（預設 10 站，模擬）。
  - `GET /`：顯示測試結果與測試站監控儀表板。
- `StationSimulator` 目前以記憶體模擬站點狀態，並在每次更新時刷新指標。

### 執行流程

1. `python main.py` 會探索 `tests/` 底下所有繼承 `BaseTest` 的類別。
2. `Runner` 以平行方式執行並回傳 `TestResult` 清單。
3. `Reporter` 產出 `reports/` 下的 HTML/JSON 報表。
4. 若設定 `--server-url`，會把結果送到 `POST /results`。
5. Dashboard 彙整測試結果與測試站資訊供監控使用。

### 測試站監控流程（預設 10 站）

1. 服務啟動時初始化 `StationSimulator(station_count=10)`。
2. 每次儀表板或 API 被呼叫時，依固定間隔刷新站點快取。
3. 站點資料包含：
   `station_id`, `line`, `status`, `current_test`, `temperature_c`,
   `utilization_pct`, `pass_count`, `fail_count`, `last_heartbeat`。
4. Dashboard 顯示狀態統計（running/idle/warning/offline）與站點明細。

---

## Supabase 整合架構（建議）

若你要讓「測試站上拋資料到 DB，Dashboard 從 DB 撈資料」，建議採用以下流程：

1. 測試站（`main.py`）執行完成後，POST 一個完整 run payload 到 `POST /results`。
2. 伺服器（`server/app.py`）做驗證與補欄位，再寫入 Supabase（Postgres）。
3. Dashboard API（`/api/results`, `/api/stations`）改成查 Supabase，而非讀記憶體 `deque`。

### 建議資料表

1. `test_runs`
- `id (uuid pk)`, `station_id`, `started_at`, `ended_at`, `summary_json`, `created_at`

2. `test_results`
- `id (uuid pk)`, `run_id (fk)`, `test_name`, `status`, `duration_sec`, `error_text`, `received_at`

3. `station_telemetry`
- `id (bigserial pk)`, `station_id`, `status`, `line`, `current_test`,
  `temperature_c`, `utilization_pct`, `pass_count`, `fail_count`, `heartbeat_at`

### 程式改造位置

1. `main.py`
- 上拋 payload 增加 `run_id`, `station_id`, `started_at`, `ended_at`, `summary`, `results`。

2. `server/app.py`
- `POST /results`：由記憶體儲存改為寫 Supabase。
- `GET /api/results`：由記憶體讀取改為查 Supabase。
- `GET /api/stations`：由模擬資料改為查最近 telemetry（可保留 fallback）。

3. `config.yaml`
- 建議新增：
  - `supabase.url`
  - `supabase.service_role_key_env`
  - `supabase.schema`（可選）

4. `requirements.txt`
- 新增 `supabase` 套件。

### 安全建議

1. `service_role_key` 只放在後端環境變數，不能放前端。
2. 前端若未來直連 Supabase，務必開啟 RLS 與唯讀 policy。
3. 建議以 `run_id` 做冪等控制（避免重送造成重複寫入）。

---

## 專案結構

```text
auto-test-platform/
|
+-- core/
|   +-- base_test.py           # Template Method: 測試基底類
|   +-- runner.py              # 平行測試執行器（ThreadPool / ProcessPool）
|   +-- retry.py               # 重試裝飾器與退避策略
|   +-- config.py              # YAML 設定載入器
|   +-- report.py              # HTML + JSON 報表生成器
|   +-- station_simulator.py   # 測試站遙測模擬器
|
+-- tests/
|   +-- unit/                  # 核心模組單元測試
|   +-- integration/           # Runner -> Report 等整合測試
|   +-- e2e/                   # 端到端情境測試
|   +-- unit/test_station_simulator.py
|   +-- integration/test_station_monitoring_api.py
|
+-- server/
|   +-- app.py                 # Flask dashboard + 結果收集 API
|
+-- main.py                    # CLI 入口（含測試探索）
+-- config.yaml                # 預設設定
+-- requirements.txt
+-- Dockerfile
+-- .github/workflows/test.yml
```

---

## 快速開始

### 1. 安裝相依套件

```bash
pip install -r requirements.txt
```

### 2. 執行全部測試

```bash
cd auto-test-platform
set -a
source .env
set +a
python main.py
```

報表會輸出到 `reports/report.html` 與 `reports/report.json`。

### 3. 使用自訂參數執行

```bash
python main.py --workers 8 --timeout 60 --report-dir /tmp/reports
```

### 4. 啟動 Dashboard 伺服器

```bash
cd /workspaces/Python_Automation_Framework/auto-test-platform
set -a
source .env
set +a
python server/app.py
# 開啟 http://localhost:5000
```

### 5. 使用 pytest 跑測試

```bash
pytest tests/ -v --tb=short
```

---

## 如何撰寫測試

繼承 `BaseTest` 並實作 `execute()`：

```python
from core.base_test import BaseTest
from core.retry import retry


class MyTest(BaseTest):
    name = "my_test"

    def setup(self):
        # 可選：測試前準備資源
        pass

    @retry(max_attempts=3, delay=0.2, exceptions=(IOError,))
    def execute(self):
        # 你的測試邏輯
        assert some_function() == expected_value

    def teardown(self):
        # 可選：測試後清理
        pass

    def skip_condition(self) -> bool:
        # 可選：回傳 True 會略過此測試
        return False
```

---

## 設定檔（`config.yaml`）

| 鍵值 | 預設值 | 說明 |
|-----|--------|------|
| `runner.workers` | `4` | 平行 worker 數量 |
| `runner.timeout` | `120` | 單一測試逾時秒數 |
| `report.output_dir` | `reports` | 報表輸出目錄 |
| `server.url` | `null` | 結果收集伺服器 URL（選填） |
| `retry.max_attempts` | `3` | 預設重試次數 |

---

## Docker

```bash
# 建置映像
docker build -t auto-test-platform .

# 執行測試
docker run --rm auto-test-platform

# 啟動 Dashboard 伺服器
docker run -p 5000:5000 auto-test-platform python server/app.py
```

---

## CI / GitHub Actions

`.github/workflows/test.yml` 會在每次 push / pull request 自動執行完整測試流程。
