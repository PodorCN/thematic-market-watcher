# Backend API Spec — Global Economic Calendar (Frontend Needs)

> 每日归档、`latest/archive/dates` 路径及两个公共页面的统一发布流程，以 `PUBLIC_PAGES_BACKEND_SPEC.md` 为准。

> 面向后端：前端为纯静态 `HTML + Chart.js`（`econ/template_calendar.html.j2`），所有数据通过 HTTP JSON 拉取，无需重新部署前端。数据每天更新一次即可。

---

## 1. 架构目标

```
[定时任务]  python econ/fetch_calendar.py --with-history  →  archive/YYYY-MM-DD/economic_calendar.json
      ↓ python econ/render_calendar.py --date YYYY-MM-DD
[Public snapshots] docs/data/economic-calendar/{latest,dates,archive} → JSON
      ↓ fetch()
[Frontend]  docs/economic_calendar.html  (Chart.js + Timeline)
```

* 前端 **不** 直连 FxStreet / Investing.com，只读取后端发布的快照
* 后端 **每天 00:10 UTC** 跑一次抓取，写入文件或 DB，前端下次请求即拿到新数据
* 前后端通过 **CORS** 打通，`Content-Type: application/json; charset=utf-8`

### GitHub Pages 生产文件

```text
docs/data/economic-calendar/
├── latest.json
├── dates.json
└── archive/
    └── 2026-08-24.json

docs/economic-calendar/archive/
└── 2026-08-24.html
```

- `latest.json` 与最新日期的 archive 内容一致。
- `dates.json` 格式为 `{"latest":"2026-08-24","dates":["2026-08-24","2026-08-23"]}`，日期降序。
- 历史 HTML 是当日数据生成的完整页面，日期选择器直接切换该文件，因此回看不会被最新数据重绘。
- `archive/YYYY-MM-DD/economic_calendar.json` 是流水线原始归档；`docs/data/...` 是 GitHub Pages 可公开读取的发布副本。

---

## 2. 核心端点

### 2.1 静态生产端点

```http
GET /data/economic-calendar/latest.json
GET /data/economic-calendar/dates.json
GET /data/economic-calendar/archive/{YYYY-MM-DD}.json
GET /economic-calendar/archive/{YYYY-MM-DD}.html
```

### 2.2 `GET /api/calendar`（可选动态服务）

**首选端点，前端所有渲染都靠它。**

**Query 参数（全部可选，有默认值）：**

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `start` | `YYYY-MM-DD` | 当天 | 区间开始（包含） |
| `end` | `YYYY-MM-DD` | `start + 6天` | 区间结束（包含） |
| `countries` | `CSV` | `US,CA,EMU,DE,FR,IT,ES,UK,CH` | FxStreet 国家码，逗号分隔 |
| `impacts` | `CSV` | `HIGH,MEDIUM` | `HIGH,MEDIUM,LOW,NONE` |
| `currencies` | `CSV` | `ALL` | `USD,CAD,EUR,JPY` 等，`ALL` 表示不过滤 |
| `with_history` | `bool` | `true` | 是否附带 `history`（Chart 需要） |
| `history_events` | `int` | `8` | 最多返回几条指标的历史 |
| `history_limit` | `int` | `12` | 每条指标取多少期 |

**示例请求**

```
GET /api/calendar?start=2026-08-24&end=2026-08-30&countries=US,CA,EMU&impacts=HIGH,MEDIUM&with_history=true
GET /api/calendar/latest   # 快捷：返回最新一天的完整 JSON（等价于最新 archive）
```

**成功响应 `200`**

```json
{
  "start": "2026-08-24",
  "end": "2026-08-30",
  "fetched_at": "2026-08-24T12:34:56.000Z",
  "source": "fxstreet",
  "countries": ["US","CA","EMU","DE","FR","IT","ES","UK","CH"],
  "impacts_filter": ["HIGH","MEDIUM"],
  "currencies_filter": null,
  "count": 52,
  "events": [ { ... } ],
  "history": { "5d9ff5c8-...": [ ... ] },
  "history_meta": { "5d9ff5c8-...": { ... } }
}
```

### 2.3 `GET /api/history?eventId=xxx&limit=12` (可选，增量加载)

如果不想把 `history` 塞进主接口，可单独拉：

```
GET /api/history?eventId=5d9ff5c8-1e0e-44b8-8d06-4ac39d217bf3&limit=12
→ [{ "dateUtc":"2026-07-30T12:30:00Z", "periodDateUtc":"2026-06-01T00:00:00Z", "actual":0.1, "consensus":0.2, "previous":0.3, "date":"2026-07-30" }, ...]
```

前端当前 **不需要** 此端点（`history` 已内嵌），提供则可实现懒加载。

### 2.4 `GET /api/health`

```json
{ "ok": true, "latest_date": "2026-08-24", "fetched_at": "2026-08-24T12:34:56Z" }
```

---

## 3. 数据 Schema（前端强依赖，请勿改名）

### 3.1 `events[]` 单条

| 字段 | 类型 | 示例 | 说明 |
|------|------|------|------|
| `id` | `string` | `"5d9ff5c8-..."` | FxStreet `eventDateId`，唯一 |
| `eventId` | `string\|null` | `"5d9ff5c8-..."` | 指标本体 ID（用于拉历史），无则 `null` |
| `datetime_utc` | `string` | `"2026-08-26T12:30:00"` | ISO8601，无时区视为 UTC |
| `date` | `string` | `"2026-08-26"` | `YYYY-MM-DD`，用于分组 |
| `time` | `string` | `"12:30"` | `HH:MM` |
| `country` | `string\|null` | `"US"` | `US/CA/EMU` |
| `currency` | `string` | `"USD"` | `USD/CAD/EUR` |
| `event` | `string` | `"Core Personal Consumption Expenditures - Price Index (MoM)"` | 指标名 |
| `title` | `string` | 同 `event` | 兼容 |
| `impact` | `string` | `"HIGH"` | `HIGH/MEDIUM/LOW/NONE` |
| `volatility` | `string` | `"HIGH"` | 同 `impact` |
| `actual` | `number\|null` | `null` | 已发布为数值，未发布 `null`（**禁止 `NaN`/`Infinity`，必须 `null`**） |
| `forecast` | `number\|null` | `0.2` | `consensus`，同上 |
| `previous` | `number\|null` | `0.1` | 同上 |
| `unit` | `string\|null` | `"%"` | `"%", "K", null` |
| `hasHistorical` | `bool\|null` | `true` | 是否有历史可拉 |
| `source` | `string` | `"fxstreet"` | |
| `url` | `string\|null` | `null` | |

**前端对 `actual/forecast/previous` 的处理**：三者任意为 `null` 即显示 `—`。数值保持中性色，不把“高于预期”解释为天然利好或利空。

### 3.2 `history` + `history_meta`

```json
"history": {
  "5d9ff5c8-1e0e-44b8-8d06-4ac39d217bf3": [
    { "dateUtc":"2026-07-30T12:30:00Z", "periodDateUtc":"2026-06-01T00:00:00Z", "actual":0.1, "consensus":0.2, "previous":0.3, "date":"2026-07-30" },
    { "dateUtc":"2026-06-25T12:30:00Z", "actual":0.3, "consensus":0.3, "previous":0.2, "date":"2026-06-25" }
  ]
},
"history_meta": {
  "5d9ff5c8-1e0e-44b8-8d06-4ac39d217bf3": { "event":"Core Personal Consumption Expenditures - Price Index (MoM)", "currency":"USD", "unit":"%", "impact":"HIGH" }
}
```

* `history` key = `eventId`，value 按时间升序（老→新）已排好，前端直接喂 `Chart.js`
* `history_meta` 提供 `event/currency/unit/impact` 用于标题

---

## 4. 后端更新策略（每天一次即可）

**推荐 Cron**

```cron
# 每天 00:10 UTC 拉未来 7 天 + 历史
10 0 * * *  cd /app && .venv/bin/python econ/fetch_calendar.py --days 7 --countries US,CA,EMU,DE,FR,IT,ES,UK,CH --impacts HIGH,MEDIUM --with-history --history-events 8 --history-limit 12
```

* 输出文件 `archive/$(date -u +%F)/economic_calendar.json`（`count: 52` 左右）
* 随后执行 `python econ/render_calendar.py --date $(date -u +%F)`，自动发布公开 JSON、历史 HTML、`latest.json` 和 `dates.json`
* HTML 由同一流水线自动生成并发布，无需人工修改页面

### 保存与保留要求

- 每个 archive 日期对应一次完整抓取视图，历史文件永久保留。
- 同一日期可因数据修订重跑并原子覆盖，但不得回写其他日期。
- 发布顺序为日归档 JSON/HTML → `latest.json` → `dates.json`。
- 如果当天抓取失败，保留上一份 `latest.json`，不要写空数组；健康状态标记 `stale: true`。
- `dates.json` 中的每个日期必须同时存在公开 JSON 和历史 HTML。

**实现最简（文件直出）**

```python
# FastAPI 示例
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import json, pathlib
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
ARCHIVE = pathlib.Path("archive")
@app.get("/api/calendar")
def get_calendar(start: str = None, end: str = None, with_history: bool = True):
    # 1. 若带参，现场调 EconomicCalendar(...).fetch(with_history=...) 实时抓
    # 2. 否则直接读最新 archive
    latest = sorted(ARCHIVE.glob("*/economic_calendar.json"))[-1]
    data = json.loads(latest.read_text(encoding="utf-8"))
    return data
```

---

## 5. 前端适配说明（已就绪）

* 当前 `econ/template_calendar.html.j2` 已改为 **全宽英文**，`main { width:100% }`，`Chart.js 4.4.3 CDN`
* 国旗用 `https://flagcdn.com/w20/{code}.png`（`FLAG_CODE: USD→us, CAD→ca, EUR→eu`），`Windows` 可靠，`emoji` 仅 fallback
* Timeline 列：`Time (Toronto) | Currency | Importance(★/★★/★★★) | Event | Actual | Forecast | Previous`
* Charts 过滤：`USD > CAD > Europe`，`AUD/JPY` 已排除，Job 数据（`Jobless Claims/ADP/Nonfarm`）已加权提升
* 前端只需把 `fetch('/archive/2026-08-24/economic_calendar.json')` 改为 `fetch('/api/calendar?with_history=true')`，其余渲染逻辑不变

**前端 JS 关键（已实现）**

```js
const res = await fetch('/api/calendar?start=2026-08-24&end=2026-08-30&with_history=true');
const { events, history, history_meta } = await res.json();
// events → 分组渲染 Timeline
// history + history_meta → Chart.js 折线（Actual 实线，Forecast 虚线延伸）
```

---

## 6. 约束与坑位

1. **禁止 `NaN/Infinity`**：`pandas` 的 `NaN` 必须 `replace → null`，否则 `JSON` 非法。参考 `econ/core.py: save_json` 的 `allow_nan → replace NaN→null`
2. **存储 UTC、展示 Toronto**：`datetime_utc` 必须为 ISO8601 UTC；渲染时统一转换到 `America/Toronto`，自动处理 EST/EDT
3. **CORS**：必须 `Access-Control-Allow-Origin: *`
4. **缓存**：`Cache-Control: public, max-age=300`（5 分钟），不必每次请求都重抓 FxStreet
5. **错误**：FxStreet 偶发 403/超时，后端应返回上一次成功缓存 + `stale: true` 标记，前端提示“数据更新延迟”

---

## 7. 验收清单（给后端自测）

- [ ] `GET /api/calendar` 返回 `count 50±10`，含 `forecast/previous` 非全 `null`（至少 `Core PCE` 有 `0.2/0.1`）
- [ ] `GET /api/calendar?countries=US,CA` 仅含 `USD/CAD`
- [ ] `history` 内至少 `4` 条（`US Core PCE MoM/YoY`, `CAD GDP` 等），每条 `12` 点且 `actual` 有值
- [ ] 响应头 `Content-Type: application/json; charset=utf-8` 且无 `NaN` 字面量
- [ ] `curl http://localhost:8000/api/calendar | jq .fetched_at` 正常

---

## 8. 示例完整 JSON（截断）

见 `archive/2026-08-24/economic_calendar.json`（52 条，8 组历史），或请求线上 `/api/calendar` 获取。
