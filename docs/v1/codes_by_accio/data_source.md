以下指令我剛才全部重跑過，輸出是實際結果（非回憶）。

## 一、TQQQ 日線 — Nasdaq 報價 API

```bash
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

curl -s -m 40 -o /tmp/tqqq.json -w "HTTP:%{http_code}  bytes:%{size_download}\n" \
  -A "$UA" -H "Accept: application/json" \
  "https://api.nasdaq.com/api/quote/TQQQ/historical?assetclass=etf&fromdate=2019-01-01&todate=2026-09-15&limit=5000"
```

```
HTTP:200  bytes:208928
```

```bash
python3 -c "
import json; d=json.load(open('/tmp/tqqq.json'))
print(list(d['data'].keys()))
r=d['data']['tradesTable']['rows']; print(len(r)); print(r[0]); print(r[-1])
"
```

```
['symbol', 'totalRecords', 'tradesTable']
1935
{'date': '09/14/2026', 'close': '69.27', 'volume': '49,910,320', 'open': '67.529', ...}
{'date': '01/02/2019', 'close': '4.6963', 'volume': '266,751,680', 'open': '4.3475', ...}
```

解析（三個要注意的坑）：

```python
import json, datetime

def load_tqqq(path):
    rows = json.load(open(path))["data"]["tradesTable"]["rows"]
    # 坑1：rows 是「新→舊」排列，index[0] 是最新一天
    # 坑2：日期是 MM/DD/YYYY，close 帶千分位逗號（'1,234.5'）
    # 坑3：close 為分割還原價（TQQQ 2025-11-20 曾 2:1 分割）
    return {datetime.datetime.strptime(r["date"], "%m/%d/%Y").date():
            float(r["close"].replace(",", "")) for r in rows}
```

## 二、Fear & Greed 歷史 — CNN 端點

```bash
curl -s -m 60 -o /tmp/fg.json -w "HTTP:%{http_code}  bytes:%{size_download}\n" \
  -A "$UA" -H "Referer: https://www.cnn.com/" \
  "https://production.dataviz.cnn.io/index/fearandgreed/graphdata/2021-09-01"
```

```
HTTP:200  bytes:886571
points: 1264 | first: 2021-09-01 43.133 | last: 2026-09-15 30.343
```

三個關鍵：路徑末端是**起始日**（不帶日期只回傳最近 1 年）；必須帶 `Referer: https://www.cnn.com/`；起始日早於 2021-09-01 會回 500 或機器人頁。回傳同時附帶 7 項子指標（`put_call_options`、`junk_bond_demand`、`market_volatility_vix` 等），要做拆解可直接取用。

```python
def load_fg(path):
    for p in json.load(open(path))["fear_and_greed_historical"]["data"]:
        # x = 毫秒 epoch，y = 0–100
        yield datetime.datetime.fromtimestamp(p["x"]/1000, datetime.UTC).date(), float(p["y"])
```

## 三、對齊 + 相關性（實跑輸出）

```python
px, fg = load_tqqq("/tmp/tqqq.json"), dict(load_fg("/tmp/fg.json"))
dates = sorted(set(px) & set(fg))          # 取交集
close = [px[d] for d in dates]; fear = [fg[d] for d in dates]; n = len(dates)

fwd20 = [close[i+20]/close[i]-1 if i+20 < n else None for i in range(n)]
tr20  = [close[i]/close[i-20]-1 if i >= 20 else None for i in range(n)]
```

```
TQQQ 1935 天 / F&G 1263 天 → 交集 1262 天  2021-09-01 ~ 2026-09-14
corr(F&G, 前20日報酬) = 0.711
corr(F&G, 後20日報酬) = -0.073
```

## 四、走不通的路徑（先幫你排除）

| 來源 | 結果 |
|---|---|
| `stooq.com/q/d/l/?s=tqqq.us&i=d` | 回 JS 驗證頁，不是 CSV |
| `query1.finance.yahoo.com/v8/finance/chart/TQQQ` | HTTP 429 |
| WSJ `historical-prices/download?MOD=mw_quote` | 無 CSV 內容 |
| CNN `graphdata/2019-01-01` | HTTP 500／機器人頁 |

最後採用 Nasdaq 報價 API + CNN production.dataviz 端點，兩者都不需 API key。完整統計、CSV 輸出、PNG 與互動 HTML 的產生流程在 `build_chart.py`，可直接 `python3 build_chart.py` 重跑（需先 `pip install matplotlib numpy`，中文標題需設 `Noto Sans CJK TC` 字型）。

指令備忘已整理成 [data_sources.md](tqqq-fear-greed/data_sources.md)，可直接複製重用。