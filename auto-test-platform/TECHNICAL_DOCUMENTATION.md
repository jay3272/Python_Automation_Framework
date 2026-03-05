# Auto-Test Platform 技術文件

## 1. 文件目的
本文件提供 `auto-test-platform` 的技術層面說明，包含系統架構、核心模組責任、資料流、API、執行方式、測試策略，以及後續擴充建議。

## 2. 專案目標
此專案是一個 Python 自動化測試框架，核心目標如下：
- 自動發現與執行測試案例
- 支援平行執行與重試機制
- 產生 HTML / JSON 報表
- 透過 Flask 提供 Dashboard 與 API
- 模擬測試站台資料（預設 10 台）供監控畫面展示

## 3. 目錄與元件

```text
auto-test-platform/
├── main.py
├── config.yaml
├── core/
│   ├── base_test.py
│   ├── runner.py
│   ├── retry.py
│   ├── config.py
│   ├── report.py
│   └── station_simulator.py
├── server/
│   └── app.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── reports/
├── requirements.txt
└── Dockerfile
```

## 4. 系統架構

### 4.1 執行層（Execution Layer）
由 `main.py` + `core/` 組成。
- `main.py`: 解析 CLI 參數、載入設定、發現測試、執行 Runner、產生報表、可選擇上傳結果
- `core.base_test.BaseTest`: 測試模板（Template Method Pattern）
- `core.runner.Runner`: 平行執行測試（ThreadPool / ProcessPool）
- `core.retry`: 提供 retry decorator 與退避策略

### 4.2 報表層（Reporting Layer）
由 `core.report.Reporter` 組成。
- 輸出 `report.html`（人類閱讀）
- 輸出 `report.json`（機器整合/CI）
- 提供測試摘要（passed/failed/error/skipped）

### 4.3 監控層（Monitoring Layer）
由 `server/app.py` + `core/station_simulator.py` 組成。
- `server/app.py` 提供 API 與 Dashboard
- `station_simulator.py` 產生站台監控資料（目前為模擬）

## 5. 執行流程

### 5.1 測試主流程
1. `python main.py`
2. `discover_tests()` 掃描 `tests/` 下所有繼承 `BaseTest` 的 class
3. `Runner.run()` 平行執行測試
4. `Reporter.generate()` 寫出 `reports/report.html` 與 `reports/report.json`
5. 若指定 `--server-url`，結果送到 `POST /results`

### 5.2 Dashboard / 監控流程
1. `python server/app.py` 啟動 Flask server
2. 站台模擬器初始化（預設 10 台，可用環境變數調整）
3. 每次進入 Dashboard 或呼叫 `/api/stations` 時更新站台快取
4. 前端頁面呈現測試結果與站台監控資訊

## 6. 關鍵模組說明

### 6.1 `core/base_test.py`
- `BaseTest.run()` 固定生命週期：
  - `skip_condition()`
  - `setup()`
  - `execute()`
  - `teardown()`
- 以 `TestResult` 統一結果格式：
  - `name`, `status`, `duration`, `error`, `details`

### 6.2 `core/runner.py`
- 接收測試類別序列，建立 executor 執行
- 支援每個測試 timeout
- 可透過 callback (`on_result`) 做即時結果處理
- `summary()` 提供統計

### 6.3 `core/report.py`
- `_counts()` 統一計數邏輯
- `generate()` 一次輸出 HTML + JSON
- 提供 CI 友善摘要輸出

### 6.4 `core/config.py`
- 讀取 YAML 設定
- 支援 dot-path 讀取，例如 `runner.workers`
- CLI 參數可覆蓋設定值

### 6.5 `core/station_simulator.py`
- 建立多個站台（預設 10 台）
- 每台包含：
  - `station_id`, `line`, `status`, `current_test`
  - `temperature_c`, `utilization_pct`
  - `pass_count`, `fail_count`, `last_heartbeat`
- `tick()` 會按狀態更新統計與健康度

### 6.6 `server/app.py`
- API:
  - `GET /health`
  - `POST /results`
  - `GET /api/results`
  - `GET /api/stations`
  - `GET /` Dashboard
- Dashboard 內容：
  - 測試結果摘要卡
  - 最近結果表格
  - 站台監控卡與站台明細表

## 7. 設定與環境變數

### 7.1 `config.yaml`
重要參數：
- `runner.workers`
- `runner.timeout`
- `report.output_dir`
- `server.url`
- `retry.max_attempts`

### 7.2 監控相關環境變數
- `ATP_STATION_COUNT`: 站台數量（預設 `10`）
- `ATP_STATION_UPDATE_SEC`: 站台資料刷新間隔（預設 `2.0` 秒）
- `ATP_MAX_RUNS`: server 儲存結果的最大筆數（預設 `100`）

## 8. 操作指令

### 8.1 初始化
```bash
cd /workspaces/Python_Automation_Framework/auto-test-platform
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 8.2 執行測試
```bash
python main.py
```

### 8.3 啟動 Dashboard（10 站台）
```bash
export ATP_STATION_COUNT=10
python server/app.py
```

### 8.4 測試結果送到 Dashboard
```bash
python main.py --server-url http://localhost:5000
```

### 8.5 呼叫監控 API
```bash
curl -s http://localhost:5000/api/stations
```

## 9. 測試策略
專案測試分層如下：
- Unit: 驗證單一模組行為（`tests/unit`）
- Integration: 驗證模組協作（`tests/integration`）
- E2E: 驗證整體流程（`tests/e2e`）

建議執行：
```bash
pytest tests/ -v --tb=short
```

## 10. 已知限制
- 站台監控資料目前為模擬資料，非真實硬體站台
- server 結果儲存為記憶體結構，重啟後資料不保留
- 目前未整合認證授權（API 無 auth）

## 11. 擴充建議
- 將 `station_simulator` 抽象化為 provider 介面，支援真實資料來源（MQTT/HTTP/DB）
- 將 `_results_store` 改為持久化儲存（PostgreSQL/Redis）
- 為 API 加上 token 或 OIDC 驗證
- 增加站台告警規則（溫度、失敗率、離線時間）
- 新增 WebSocket 讓 Dashboard 即時更新，減少整頁 refresh

## 12. 文件維護
當以下項目變更時，請同步更新本文件：
- API 路由或 payload 結構
- 配置鍵值與預設值
- 架構分層與模組責任
- 監控資料模型與更新邏輯
