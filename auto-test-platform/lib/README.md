# lib Supabase Connection Module

這份文件說明 `lib/supabase_connection.py` 的用途與使用方式。

## 目標

- 先提供一個可獨立驗證的 Supabase 連線模組。
- 不耦合 `core/` 現有 uploader 流程。
- 讓你可以先測試、再評估是否取代現行實作。

## 提供的類別

- `SupabaseRestConnection`
: 建立 Supabase REST API endpoint、headers、POST request。
- `SupabaseDatabaseConnection`
: 透過 `DATABASE_URL` 建立 asyncpg 連線，並提供連線健康檢查。

## 1. REST 模式使用方式

```python
import json
import urllib.request

from lib.supabase_connection import SupabaseRestConnection

conn = SupabaseRestConnection(
    supabase_url="https://your-project.supabase.co",
    service_role_key="YOUR_SERVICE_ROLE_KEY",
    schema="public",
)

payload = json.dumps([
    {
        "run_id": "run-2026-001",
        "station_id": "ST-001",
    }
]).encode("utf-8")

request = conn.build_post_request(
    table="test_runs",
    payload=payload,
    query={"on_conflict": "run_id"},
    prefer="resolution=merge-duplicates,return=representation",
)

with urllib.request.urlopen(request, timeout=conn.timeout_sec) as response:
    body = response.read().decode("utf-8")
    print(body)
```

## 2. DATABASE_URL 模式使用方式

```python
import asyncio

from lib.supabase_connection import SupabaseDatabaseConnection


db = SupabaseDatabaseConnection(
    database_url="postgresql://postgres:password@db.host:5432/postgres",
    schema="public",
    timeout_sec=15.0,
)

# 同步健康檢查（CLI 或 script 常用）
db.ping()


# 非同步連線（需要自行關閉連線）
async def run():
    conn = await db.connect()
    try:
        await conn.execute("SELECT 1;")
    finally:
        await conn.close()

asyncio.run(run())
```

## 參數說明

- `supabase_url`
: Supabase 專案 URL，例如 `https://xxx.supabase.co`。
- `service_role_key`
: 後端使用的 service role key。
- `database_url`
: Supabase Postgres 連線字串。
- `schema`
: 預設 `public`，僅允許 `A-Z a-z 0-9 _` 組成的合法 schema 名稱。
- `timeout_sec`
: 連線或請求 timeout 秒數。

## 安全建議

- `service_role_key` 只放在後端環境變數，不要放前端。
- 不要把 key 寫死在 repo。
- 若之後改由前端直連，請務必配置 RLS 與最小權限 policy。

## 測試

目前有獨立單元測試：

```bash
pytest tests/unit/test_lib_supabase_connection.py -q
```
