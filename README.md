# Liquidity & Sentiment — 市場狀態解讀系統 (Market Regime Interpretation System)

本專案整合美國總體流動性（Macro Liquidity）、金融情勢（Financial Conditions）、信用利差（Credit Spread）與市場情緒指標（Market Sentiment），從資料抓取、時效性檢核、資料清洗與指標衍生計算，最終透過互動式儀表板（Interactive Dashboard）呈現當前市場狀態與歷史脈絡。

---

## 1. 核心設計哲學

本系統並非單純將 CSV 畫成圖表牆，而是遵循以下優先順序建立的 **Market Regime Interpretation System**：

> **Clarity > Interpretation > Historical Context > Completeness > Decoration**  
> **Current State → Trend → Historical Context → Drivers → Details**

系統設計符合 **5 / 15 / 30 秒法則**：
- **5 秒內**：由頂部 **Market Regime Banner** 立即掌握當前市場處於何種狀態（`Risk-On` / `Neutral` / `Mixed` / `Transitional` / `Risk-Off`）及資料可信度（Confidence）。
- **15 秒內**：由四大支柱（Liquidity、Sentiment、Financial Conditions、Market Stress）與 6 張核心 KPI 卡掌握各維度的方向與變化。
- **30 秒內**：由 **Current vs Historical Matrix** 與各分區圖表理解造成當前狀態的主要驅動因子（如 TGA 抽水、HY OAS 利差變化）及其歷史分位數（Historical Percentile）。
- **2–5 分鐘以上**：透過四象限軌跡圖、滾動相關性、歷史狀態時間軸（Regime Timeline）與可排序/篩選的明細表進行深度 Drill-down。

---

## 2. 快速開始 (Quick Start)

### 方式 A：直接開啟互動式儀表板（無須啟動伺服器）
儀表板已將處理後的資料封裝於 [`dashboard/data.js`](file:///Users/ryanyang/my_code/code/Projects/Project.sentiment_n_liquidity/dashboard/data.js)，支援 `file://` 直接開啟：

```bash
open /Users/ryanyang/my_code/code/Projects/Project.sentiment_n_liquidity/dashboard/index.html
```

### 方式 B：從最新 CSV 重新建置儀表板資料
當有新的 `sentiment_n_liquidity_YYYY-MM-DD.csv` 產出時，執行資料處理管線即可自動更新 `dashboard/data.js`：

```bash
cd /Users/ryanyang/my_code/code/Projects/Project.sentiment_n_liquidity/dashboard
python3 build_dashboard.py
```

若要指定特定日期的 CSV 檔案：

```bash
python3 build_dashboard.py ../sentiment_n_liquidity_2026-10-17.csv
```

### 方式 C：執行上游資料抓取與合併管線
若要從各官方資料源（FRED、NY Fed、Chicago Fed、Yahoo Finance、CNN、AAII、CBOE、FINRA）重新抓取最新數據並合成 CSV：

```bash
cd /Users/ryanyang/my_code/code/Projects/Project.sentiment_n_liquidity
python3 sentiment_n_liquidity.py
```

---

## 3. 專案架構與檔案說明

```text
Project.sentiment_n_liquidity/
├── README.md                                   # 專案說明文件（本檔案）
├── PROMPT for sentiment & liquidity.md         # 系統設計與金融分析規格書
├── sentiment_n_liquidity_2026-10-17.csv        # 合併後之歷史市場資料集（原始 CSV，絕不直接修改）
├── sentiment_n_liquidity_2026-10-17_status.csv # 資料最新時效性與前值填補狀態檢核表
├── sentiment_n_liquidity.py                    # 上游資料抓取與合併主程式
├── indicators_n_sp500_historical_data.py       # 情緒與市場指標抓取模組（SPX, VIX, AAII, CNN, P/C, EFFR, Breadth）
├── liquidity_monitor.py                        # 流動性與信用指標抓取模組（WALCL, TGA, RRP, NFCI, HY OAS, FINRA）
├── data_freshness.py                           # 資料發布時程與時效性自動標注模組
└── dashboard/                                  # 互動式市場狀態儀表板
    ├── indicator_config.py                     # 集中化指標設定檔（名稱、單位、原始頻率、清洗規則、方向、閾值）
    ├── build_dashboard.py                      # 資料處理管線（Raw → Cleaning → Derived → Regime → data.js）
    ├── data.js                                 # 由管線自動產出的結構化前端資料檔
    ├── index.html                              # 儀表板主頁面（5 層資訊架構）
    ├── styles.css                              # 響應式樣式表（含 Container Queries 與語意化色彩）
    └── app.js                                  # 前端互動邏輯與 ECharts 圖表渲染模組
```

---

## 4. 資料處理管線與資料完整性原則 (Data Integrity Rules)

本系統嚴格遵守 **Data Integrity Rules**，絕不修改原始 CSV、不自行創造歷史資料、不將缺失值當作 `0`、不在圖表上對缺失區間進行平滑插補：

```text
RAW CSV DATA (sentiment_n_liquidity_*.csv)
    ↓
DATA CLEANING (還原上游合併時產生之 Forward-Fill)
    ↓
DATA TRANSFORMATION (As-of 對齊、Horizon 變化量 Δ、歷史分位數 Percentile)
    ↓
DERIVED METRICS (週度流動性歸因、Sentiment Composite、Market Stress 指標)
    ↓
REGIME CLASSIFICATION (四大支柱判定 + 整體 Regime 與 Transitional 轉折偵測)
    ↓
VISUALIZATION (data.js → index.html / app.js)
```

### 4.1 清洗規則（還原真實觀測頻率）
由於上游 `sentiment_n_liquidity.py` 在將週頻與日頻資料合併至每日時間軸時進行了前值填補（Forward-Fill），[`build_dashboard.py`](file:///Users/ryanyang/my_code/code/Projects/Project.sentiment_n_liquidity/dashboard/build_dashboard.py) 依據 [`indicator_config.py`](file:///Users/ryanyang/my_code/code/Projects/Project.sentiment_n_liquidity/dashboard/indicator_config.py) 中的設定執行清洗：
- **`collapse_runs`**（適用於週頻指標：`Fed_Assets_B`、`NFCI`、`AAII_Spread`）：僅保留每次數值更新的第一筆日期（即真實發布/基準日），使週頻資料回到真實的週度觀測點（例如 `AAII` 由 9,878 筆還原為 2,031 筆真實週度調查；`WALCL` 與 `NFCI` 還原為 158 與 152 筆週度觀測）。
- **`drop_repeats`**（適用於高精確度日頻指標：`Net_Liquidity`、`TGA`、`Reverse_Repo`、`HY_Spread`、`CNN_FearGreed`）：移除因假日或 T+1 發布時差所產生的連續重複填補值。
- **`none`**（適用於 `SP500_Close`、`VIX`、`PC_Ratio`、`Fed_Rate`、`Breadth_Ratio`、月頻 `FINRA Margin`）：保留原始非空觀測值。

### 4.2 不同資料涵蓋期間（Data Coverage）之透明揭露
資料集中各指標的歷史長度差異極大：
- **長期歷史（30–39 年）**：`SP500_Close`（1987–）、`AAII_Spread`（1987–）、`VIX`（1990–）、`PC_Ratio`（1995–）。
- **中期歷史（5–26 年）**：`Fed_Rate`（2000–）、`Breadth_Ratio`（2003–）、`FINRA Margin`（2020–）、`CNN_FearGreed`（2021-10–）。
- **短期歷史（約 3 年）**：`Net_Liquidity`、`Fed_Assets_B`、`TGA`、`Reverse_Repo`、`NFCI`、`HY_Spread` 在本 CSV 中皆自 **`2023-10-17`** 起算。

**處理原則**：
1. 每個圖表標題右上角與矩陣表格皆明確標示 `Available: YYYY-MM-DD → YYYY-MM-DD` 及真實觀測點數量。
2. 所有歷史分位數（Historical Percentile）皆註明計算母體期間（例如 `since 1990` vs `since 2023-10-17 (~3Y only)`），並對少於 5 年歷史的指標標示 `Low` 資料品質（Data Quality）提醒使用者該分位數僅反映 QT 時期區間。

---

## 5. 指標分級與遴選 (Indicator Ranking)

| 等級 | 指標名稱 | 原始欄位 | 單位 | 頻率 | 用途與說明 |
|---|---|---|---|---|---|
| **Core** | Net Liquidity | `Liquidity_Net_Liquidity` | USD bn | Daily* | 聯準會淨流動性（`WALCL − TGA − RRP`），衡量體系可用準備金規模與方向 |
| **Core** | Chicago Fed NFCI | `Liquidity_NFCI` | index | Weekly | 全國金融情勢指數（`0` 為 1971 年以來均值，`< 0` 表寬鬆、`> 0` 表緊縮） |
| **Core** | High-Yield OAS | `Liquidity_HY_Spread` | % | Daily | 美國高收益債利差，衡量企業信用壓力與風險溢酬 |
| **Core** | VIX | `Sentiment_VIX` | pts | Daily | S&P 500 30 天隱含波動率，衡量機構避險需求與恐慌程度 |
| **Core (衍生)** | Sentiment Composite | 衍生指標 | 0–100 | Daily | 綜合情緒分位數（整合 `VIX` 反向、`AAII`、`Put/Call` 10 日均線反向） |
| **Secondary** | Fed Total Assets | `Liquidity_Fed_Assets_B` | USD bn | Weekly | 聯準會資產負債表規模（H.4.1 週三水準），解釋 QT/QE 貢獻 |
| **Secondary** | Treasury General Account | `Liquidity_TGA` | USD bn | Daily | 財政部存放於 Fed 帳戶餘額（上升代表從市場抽走流動性） |
| **Secondary** | ON Reverse Repo | `Liquidity_Reverse_Repo` | USD bn | Daily | 隔夜逆回購餘額（下降代表閒置資金釋出回金融體系） |
| **Secondary** | AAII Bull–Bear Spread | `Sentiment_AAII_Spread` | pp | Weekly | 散戶看多減看空比例差 |
| **Secondary** | CBOE Total Put/Call | `Sentiment_PC_Ratio` | ratio | Daily | 選擇權賣權/買權成交量比（含 10 日移動平均） |
| **Secondary** | CNN Fear & Greed | `Sentiment_CNN_FearGreed` | 0–100 | Daily | 作為情緒交叉比對指標（因已內含 VIX、P/C、HY 且僅自 2021 起，不重複納入 Composite） |
| **Detail** | S&P 500 Close | `Sentiment_SP500_Close` | index | Daily | 大盤指數背景對照（不納入 Regime 判定規則，避免循環論證） |
| **Detail** | Effective Fed Funds Rate | `Sentiment_Fed_Rate` | % | Daily | 聯邦基金有效利率（貨幣政策背景） |
| **Detail** | Breadth Proxy (`RSP/SPY`) | `Sentiment_Breadth_Ratio` | ratio | Daily | 等權重與市值加權 ETF 比值；因絕對水準具長期結構性漂移，僅對 **91 天變化量**計算分位數 |
| **Detail** | FINRA Margin & Free Credit | `Liquidity_Margin_*` (3 欄) | USD mn | Monthly | 融資餘額與客戶現金/融資帳戶閒置餘額（月頻槓桿背景指標） |
| **Hidden** | 重複與文字欄位 | `Liquidity_Fed_Assets`, `Liquidity_TGA_B`, `Liquidity_Margin_Year-Month` | — | — | 與現有欄位完全重複（1000 倍單位差或 1:1 相等）或純文字月份標籤，不作視覺化 |

---

## 6. 市場狀態與衍生指標方法論 (Methodology)

所有參數集中定義於 [`dashboard/indicator_config.py`](file:///Users/ryanyang/my_code/code/Projects/Project.sentiment_n_liquidity/dashboard/indicator_config.py) 的 `REGIME_PARAMS`：

### 6.1 趨勢訊號 (Trend Signal $z$)
針對每個指標設定合理的觀察期 $h$（流動性/信用/NFCI/AAII 為 `91` 個日曆天 ≈ 3 個月；日頻情緒指標為 `30` 天；月頻融資為 `365` 天）：
1. 以 Backward As-of 方式尋找 $t - h$ 當日或之前最近一筆真實觀測值，計算變化量 $\Delta_t = x_t - x_{t-h}$。
2. 除以該指標全歷史變化量的標準差 $\sigma(\Delta)$，得出標準化動能訊號 $z_t = \Delta_t / \sigma(\Delta)$。
3. 若 $|z_t| < 0.5$，判定為 `Stable` / `Neutral`；若 $z_t \ge +0.5$ 為顯著上升，$z_t \le -0.5$ 為顯著下降。

### 6.2 四大支柱分類規則
1. **Liquidity Regime（流動性狀態）**
   - 依據 `Net Liquidity` 的 91 天趨勢訊號 $z_{\text{NL}}$：
   - $z_{\text{NL}} > +0.5 \Rightarrow$ **`Expanding`**（擴張）
   - $z_{\text{NL}} < -0.5 \Rightarrow$ **`Contracting`**（收縮）
   - 其餘 $\Rightarrow$ **`Neutral`**（持平）
   - *註：不建立數字型 Liquidity Composite Score，以避免 3 年短期樣本與跨頻率混算造成的假精確（False Precision）。*
2. **Financial Conditions（金融情勢）**
   - 取 `NFCI` 91 天趨勢訊號與 `HY OAS` 91 天趨勢訊號之平均 $z_{\text{FC}}$：
   - $z_{\text{FC}} < -0.5 \Rightarrow$ **`Easing`**（趨於寬鬆）
   - $z_{\text{FC}} > +0.5 \Rightarrow$ **`Tightening`**（趨於緊縮）
   - 其餘 $\Rightarrow$ **`Neutral`**（持平）
3. **Sentiment Regime & Sentiment Composite（市場情緒）**
   - **組成**：等權重平均三項長歷史指標之全樣本分位數（方向統一為高 = Greed）：
     1. `100 − Percentile(VIX)`（1990–）
     2. `Percentile(AAII Bull–Bear Spread)`（1987–，以 12 天容許範圍 As-of 對齊至交易日）
     3. `100 − Percentile(Put/Call 10D Mean)`（1995–）
   - 至少需具備 2 項有效成分始計算平均，並將合成序列重新排序為 `0–100` 整數分位數。
   - `< 25` $\Rightarrow$ **`Fear`**；`> 75` $\Rightarrow$ **`Greed`**；`25–75` $\Rightarrow$ **`Neutral`**。
4. **Market Stress（市場壓力）**
   - 取 `VIX` 歷史分位數與 `HY OAS` 歷史分位數之平均：
   - `< 50` $\Rightarrow$ **`Low`**；`50–79` $\Rightarrow$ **`Medium`**；`>= 80` $\Rightarrow$ **`High`**。

### 6.3 Overall Market Regime（整體市場狀態）
將四大支柱轉換為風險偏好投票分數：
- **正向票（`+1`）**：`Expanding`、`Easing`、`Greed`、`Low Stress`
- **負向票（`-1`）**：`Contracting`、`Tightening`、`Fear`、`High Stress`
- **中性票（`0`）**：`Neutral`、`Medium Stress`

判定邏輯：
- **`Risk-On`**：總分 $\ge +2$ 且無任何 `-1` 負向票。
- **`Risk-Off`**：總分 $\le -2$ 且無任何 `+1` 正向票。
- **`Mixed`**：同時存在至少一個 `+1` 與至少一個 `-1`（指標訊號衝突）。
- **`Neutral`**：其他非衝突之中性組合。
- **`Transitional`（轉折過渡期）**：當日基底狀態與前 `20` 個交易日的主導狀態（Mode）不同，且當日狀態在前 20 日出現比例 `< 50%`。
- **`Insufficient Data`**：有效支柱少於 3 項（例如 `2023-10-17` 之前缺乏流動性與信用資料時）。

---

## 7. 互動功能一覽

- **全域時間區間同步控制**：支援 `1M`、`3M`、`6M`、`YTD`、`1Y`、`3Y`、`5Y`、`10Y`、`MAX` 及自訂起訖日期（`Custom`），一鍵同步更新所有圖表與明細表；提供 `Reset` 鍵快速還原。
- **流動性成分切換**：可於「週度變化貢獻堆疊圖（`Contributions`：顯示 $\Delta\text{WALCL}$、$-\Delta\text{TGA}$、$-\Delta\text{RRP}$ 對淨流動性的推拉）」與「原始餘額雙軸圖（`Levels`）」間切換。
- **Liquidity × Sentiment 四象限與軌跡**：X 軸支援切換「流動性分位數（`Level`）」或「流動性 3M 動能訊號（`Momentum`）」，並標示最近 13 週移動軌跡與當前位置。
- **滾動相關性（Rolling Correlation）**：呈現週度變化量在 `13W (~90D)`、`26W (~6M)`、`52W (~1Y)` 的 Pearson 相關係數（明確標註 *Correlation ≠ Causation*）。
- **可排序、篩選與匯出之明細表**：支援依時間範圍、Regime 狀態、是否具備流動性資料進行篩選，支援自訂顯示欄位、欄位點擊排序，以及一鍵匯出篩選後 CSV。

---

## 8. 投資解讀邊界聲明 (Disclaimer)

本系統定位為 **市場狀態解讀與分析工具（Market Analysis Tool）**，而非預測引擎（Prediction Engine）。儀表板與報告中的所有文字僅描述**當前觀測條件、歷史分位數脈絡、近期趨勢與統計相關性**，不構成任何投資建議，亦不對未來股價漲跌、經濟衰退或央行政策做出絕對預測。
