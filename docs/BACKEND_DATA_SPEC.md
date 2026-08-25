# Fed × BOC 拔河看板 — 后端数据接口规格

> 每日归档、`latest/archive/dates` 路径及两个公共页面的统一发布流程，以 `PUBLIC_PAGES_BACKEND_SPEC.md` 为准。

> 前端：`docs/feds-boc-watcher.html`（已 full-width、多伦多 EDT、0–3权重、刻度 -3~+3、按权重排序、动态绳结）
> 目标：后端每日更新 **数据 JSON**，前端无改代码自动重绘。
> 更新频率：每日 08:00 多伦多（EDT, UTC-4）或事件触发（数据发布后 5 分钟内）。

---

## 1. 总览

前端不再 hardcode 驱动与预期，改为 `fetch()` 拉取后端 JSON。

**生产读取端点**
```
GET /data/fed-boc/latest.json
GET /data/fed-boc/dates.json
GET /data/fed-boc/archive/{YYYY-MM-DD}.json
```

- `latest.json`：最新完整看板，默认页面读取。
- `dates.json`：所有可回看日期，驱动页面顶部日期选择器。
- `archive/{date}.json`：指定多伦多自然日的完整不可跨日快照。
- `docs/data/fed-boc-dashboard.json`：生成流程的暂存输入；归档命令校验后才发布到上述路径。

**方案 B — 多文件拆分（可选）**
```
GET /data/meetings.json
GET /data/drivers.json          # Fed + BOC drivers
GET /data/market.json
GET /data/calendar.json         # upcoming 15条
GET /data/history.json
```

本文所有完整看板 JSON 均使用同一 schema；`latest.json` 与每日 archive 结构完全一致。

---

## 2. 文件位置与部署

- 静态站（GitHub Pages / Nginx）：公开目录为 `docs/data/fed-boc/`
- 动态服务（FastAPI/Flask）：暴露 `GET /api/v1/dashboard` 返回同结构 JSON，CORS 允许前端域
- 版本：`as_of` ISO8601 + `version` 递增，前端比对后决定是否刷新

```text
docs/data/
├── fed-boc-dashboard.json        # 暂存输入
└── fed-boc/
    ├── latest.json               # 最新完整数据
    ├── dates.json                # 日期索引
    └── archive/
        └── 2026-08-24.json       # 当日完整快照
```

`dates.json` 必须为：

```json
{
  "latest": "2026-08-24",
  "updated_at": "2026-08-24T12:00:00Z",
  "dates": ["2026-08-24", "2026-08-23"]
}
```

`dates` 按日期降序，且每个日期必须存在对应的 `archive/{date}.json`。

---

## 3. 顶层结构

```json
{
  "as_of": "2026-08-24T08:00:00-04:00",
  "version": "2026-08-24-001",
  "timezone": "America/Toronto",
  "meetings": { "fed": {}, "boc": {} },
  "drivers": { "fed": { "dovish": [], "hawkish": [] }, "boc": { "dovish": [], "hawkish": [] } },
  "market": { "since": "2026-07-30", "as_of_close": "2026-08-21T16:00:00-04:00", "tickers": [] },
  "calendar": [],
  "history": []
}
```

---

## 4. `meetings` — 会议与市场定价

```json
"meetings": {
  "fed": {
    "label": "Fed · 9/16–17 FOMC",
    "date_start": "2026-09-16",
    "date_end": "2026-09-17",
    "decision_time_toronto": "2026-09-17T14:00:00-04:00",
    "last_meeting": { "date": "2026-07-30", "decision": "维持 4.25–4.50%", "note": "3票鹰派反对未加息" },
    "pricing": {
      "cut_25bp": 0.64,
      "hold": 0.34,
      "hike_25bp": 0.02,
      "source": "CME FedWatch",
      "implied_rate_before": 4.33,
      "implied_rate_after": 4.08
    }
  },
  "boc": {
    "label": "BOC · 9/17 决议",
    "date": "2026-09-17",
    "decision_time_toronto": "2026-09-17T09:45:00-04:00",
    "last_meeting": { "date": "2026-07-30", "decision": "维持 2.75%", "note": "贸易不确定性抵消国内韧性" },
    "pricing": { "cut_25bp": 0.41, "hold": 0.54, "hike_25bp": 0.05, "source": "OIS", "implied_before": 2.75, "implied_after": 2.61 }
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `pricing.cut_25bp` 等 | number 0–1 | 是 | 概率，前端直接 `*100%` 画条 |
| `decision_time_toronto` | ISO8601 with offset | 是 | 前端倒计时与日历共用，**必须带 -04:00** |

---

## 5. `drivers` — 驱动卡片（核心）

> **前端逻辑：** 按 `weight` 降序渲染，左=鸽 右=鹰；中轴净差 = Σ鹰 - Σ鸽，映射到 -3~+3 刻度；`weight` 0–3、0.5一档、1.5为中枢正态，大部分 1.0–2.0，2.5≈必加息（当前无）、3=单事件决胜。

```json
"drivers": {
  "fed": {
    "dovish": [
      {
        "id": "fed_dove_nfp_20260808",
        "icon": "👷",
        "title": "劳动市场转弱信号",
        "published_at_toronto": "2026-08-08T08:30:00-04:00",
        "source": "BLS · 非农",
        "source_url": "https://www.bls.gov/...",
        "importance": "HIGH",
        "weight": 2.0,
        "weight_breakdown": { "deviation": 0.8, "importance": 0.8, "surprise": 0.4 },
        "data": {
          "actual": "-2.3万",
          "actual_raw": -23000,
          "forecast": "+8.0万",
          "forecast_raw": 80000,
          "previous": "+14.7万→+9.3万",
          "previous_raw": 93000,
          "delta_label": "miss -10.3万",
          "delta_type": "miss"
        },
        "reason": "为何是降息 driver？非农由韧性直接转负，且前两月合计下修...",
        "market_validation": [
          { "ticker": "RUT", "label": "罗素 -1.65% w", "type": "down" }
        ],
        "tags": ["HIGH", "非农"]
      }
    ],
    "hawkish": [ { "id": "fed_hawk_services_20260821", "weight": 2.0, "published_at_toronto": "2026-08-21T09:45:00-04:00", "data": { "actual": "56.8", "forecast": "54.0", "previous": "54.3", "delta_label": "beat +2.8", "delta_type": "beat" }, "reason": "...", "importance": "HIGH" } ]
  },
  "boc": { "dovish": [], "hawkish": [] }
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | string | 是 | 稳定唯一，如 `fed_hawk_tariff_20260822` |
| `icon` | string | 是 | emoji，前端直接渲染 |
| `title` | string | 是 | 卡片标题 |
| `summary` | string | 是 | **一句话英文结论**（如 "Job market is cracking: payrolls went negative."），卡片标题下方大号加粗展示；必须直白说明该数据意味着什么，数据细节交给 `data` 与 `reason` |
| `published_at_toronto` | ISO8601 -04:00 | **是** | **发布时间（多伦多）**，前端标题右侧 `· YYYY-MM-DD HH:MM 多伦多` 直接展示 |
| `source` / `source_url` | string | 否 | 点击卡片跳转 |
| `importance` | `HIGH`/`MEDIUM`/`LOW` | 是 | 影响徽标颜色 |
| `weight` | number 0–3 step 0.5 | **是** | 前端排序与绳结计算唯一依据；**大部分 1.0–2.0，均值 1.5 正态；2.5≈必加息，3=单事件决胜，当前不应出现 2.5+** |
| `weight_breakdown` | {deviation, importance, surprise} | 否 | 可选，前端 tooltip 展示三因子（和=weight） |
| `data` | object | 是 | **重点展示区** |
| `data.actual` / `forecast` / `previous` | string | 是 | 格式化展示，前端三栏 `实际/预期/前值` |
| `data.actual_raw` 等 | number | 否 | 供前端计算偏离幅度 |
| `delta_label` / `delta_type` | string / `beat`/`miss`/`neutral` | 是 | 如 `beat +2.8` 红/绿 pill |
| `reason` | string | 是 | “为何是 driver” 解释，前端灰底左竖线 |
| `market_validation` | array | 否 | ETF/收益率验证，如 `XLI -3.4% w` |

**数量不限：** 后端返回多少前端就渲染多少，不强行 4:4。空数组则该侧显示“暂无显著驱动”。

**排序：** 后端可已排序，前端仍会按 `weight` 降序二次排序（权重高越靠近中线）。

---

## 6. `market` — 会后市场验证

```json
"market": {
  "since": "2026-07-30",
  "as_of_close": "2026-08-21T16:00:00-04:00",
  "tickers": [
    { "symbol": "SPY", "price": 765.72, "chg_1d": 0.0041, "chg_1w": -0.0143, "label_1d": "+0.41% Fri", "label_1w": "-1.43% w", "type_1d": "up", "type_1w": "down" },
    { "symbol": "TLT", "price": 82.05, "chg_1d": -0.0035, "label_1d": "-0.35% Fri", "type_1d": "down" }
  ]
}
```

前端横向 pill 条，`up=绿 down=红`。

---

## 7. `calendar` — 接下来关键发布（预期 vs 前值）

```json
"calendar": [
  {
    "id": "core_pce_20260826",
    "datetime_toronto": "2026-08-26T08:30:00-04:00",
    "datetime_utc": "2026-08-26T12:30:00Z",
    "currency": "USD",
    "country": "US",
    "event": "Core PCE (MoM / YoY)",
    "impact": "HIGH",
    "forecast": { "mom": "0.20%", "yoy": "2.80%", "mom_raw": 0.002, "yoy_raw": 0.028 },
    "previous": { "mom": "0.26%", "yoy": "2.81%" },
    "logic": "Core PCE >0.30% MoM → 鹰派绳结+5%；≤0.20% → 鸽派反攻",
    "hawk_if": "高→鹰",
    "dove_if": "低→鸽"
  }
]
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `datetime_toronto` | **是** | 前端表格 `时间 多伦多` 列直接展示，**必须 -04:00** |
| `datetime_utc` | 是 | 供倒计时计算（前端 `new Date(datetime_utc)`） |
| `currency` | 是 | `USD`/`CAD` 供筛选 |
| `impact` | 是 | `HIGH`/`MEDIUM`/`LOW` 决定行背景色 |
| `forecast` / `previous` | 是 | 字符串展示 + `*_raw` 数值可选 |
| `logic` | 是 | “驱动逻辑” 灰底说明 |
| `hawk_if` / `dove_if` | 否 | 表格最后一列徽标 |

前端筛选：USD / CAD / HIGH，搜索 `event`，日期下拉 `datetime_toronto` 的 `YYYY-MM-DD`。

---

## 8. `history` — 历史照镜子（可选，后端可静态）

```json
"history": [
  {
    "id": "fed_2019_midcycle",
    "bank": "fed",
    "title": "Fed 2019 中期调整 · 预防式降息 3次",
    "period": "2018Q4–2019Q3",
    "similarity": 0.86,
    "tag": "相似度 86%",
    "table": [
      { "metric": "ISM 制造", "then": "47.8 收缩", "now": "48.7 收缩", "verdict": "同为 miss" }
    ],
    "verdict": "当时怎么选：Fed 先鹰(2018加息4次至2.50%) → 后鸽...",
    "verdict_type": "dove",
    "lesson": "对本次借鉴：若 Core PCE ≤2.8% 且初请破 24万..."
  }
]
```

前端卡片左红/蓝上描边，`verdict_type` 决定底色。

---

## 9. 前端渲染约定

- **时间：** 一律展示 `published_at_toronto` / `datetime_toronto` 的 `YYYY-MM-DD HH:MM 多伦多`，不再展示 UTC
- **权重：** 前端按 `weight` 降序；绳结位置 = `净差 = Σ鹰 - Σ鸽` 映射到 `-3~+3` 刻度：`pos = (3 - net)/6*100%`（+3=顶0%, +1.5=25%, 0=50%, -1.5=75%, -3=底100%）
- **刻度：** 中轴固定 5 档 `+3/+1.5/0/-1.5/-3`，气泡显示 `净 +X.X 鹰/鸽`
- **排序：** 后端无需强制排序，前端会二次排序
- **空态：** 某侧 `[]` 则显示“暂无显著驱动（权重<1.0已过滤）”

---

## 10. 后端更新流程建议

1. **09:00 多伦多** 定时任务：拉 yfinance（SPY/QQQ/XLF/XLE/XLU/TLT/GLD/ZEB.TO）、fxstreet/StatsCan/BLS/BEA、CME FedWatch/OIS
2. 计算 `weight = deviation(0–1.2) + importance(0.5–1.0) + surprise(0–0.8)` 四舍五入到 0.5，**截断 0–3**，**强制均值≈1.5**（校准：若均值>1.7则整体 -0.5）
3. 生成完整 JSON，原子写入 `docs/data/fed-boc-dashboard.json`
4. 执行 `python econ/archive_fed_boc.py`，发布 `archive/{date}.json`、`latest.json` 与 `dates.json`
5. 前端默认每 5 分钟轮询 `latest.json`；查看历史日期时停止覆盖历史画面

### 保存与保留要求

- `snapshot_date` 取每日任务在 `America/Toronto` 的运行日期；`as_of` 继续表示上游数据实际更新时间，两者不得混用。
- 发布文件增加 `snapshot_date`、`archived_at`、`stale`。即使休市日数据未变，也保存当天页面快照；当 `as_of` 早于快照日时 `stale=true`。
- 同一天事件后重跑可更新当天快照；不得修改其他日期的文件。
- 历史快照永久保留，不做滚动删除。若以后需要冷存储，manifest 中的日期和文件必须同步迁移。
- 发布顺序必须是 `archive` → `latest` → `dates`，并使用临时文件 + rename，避免前端读到半个 JSON。
- JSON 禁止 `NaN`、`Infinity`；关键字段缺失时归档命令必须失败，不能覆盖最后一份成功数据。

---

## 11. 示例完整 JSON（精简）

生产数据见 `docs/data/fed-boc-dashboard.json`；精简示例见 `docs/data/fed-boc-dashboard.example.json`。

---

## 12. 前端 fetch 示例

```js
async function load() {
  const dates = await fetch('data/fed-boc/dates.json', { cache: 'no-store' }).then(r => r.json());
  const selected = dates.latest; // 或用户选择的历史日期
  const url = selected === dates.latest
    ? 'data/fed-boc/latest.json'
    : `data/fed-boc/archive/${selected}.json`;
  const res = await fetch(url, { cache: 'no-store' });
  const j = await res.json();
  // j.meetings.fed.pricing.cut_25bp -> 概率条
  // j.drivers.fed.dovish.sort((a,b)=>b.weight-a.weight) -> 左侧
  // net = sum(hawkish.weight) - sum(dovish.weight)
  // pos = (3 - net)/6*100
  // j.calendar -> 表格
  document.querySelector('#as_of').textContent = new Date(j.as_of).toLocaleString('zh-CN', { timeZone: 'America/Toronto' });
}
load();
setInterval(load, 5*60*1000);
```

---

## 13. 联系

- 前端文件：`docs/feds-boc-watcher.html:1`
- 问题：权重 2.5≈必加息，当前不应出现；大部分 1.5 正态；时间一律多伦多 EDT。
