# 🐂 古牛量化分析系统

三个量化策略（均线金叉 / 低估值价值 / 动量反转）+ 美股 / A股 / 港股数据
+ **历史回测引擎** + 可视化页面。

---

## 快速启动（Windows）

```bat
:: 双击 start.bat，或在项目目录执行：
start.bat
```

启动后打开浏览器访问：**http://127.0.0.1:5888**

### 手动启动

```bat
pip install -r requirements.txt
python app.py
```

### macOS / Linux

```bash
bash start.sh
```

---

## 功能

### 1. 实时评分（开始分析）
输入股票代码 → 抓取近 150 天行情 → 三策略打分 → 综合建议。

### 2. 历史回测（新增 ✨）
点「历史回测」→ 在过去约 600 个交易日上模拟交易，输出：

- **总收益 / 年化收益 / 夏普比率 / 最大回撤**
- **交易次数 / 胜率**
- 策略净值曲线 vs **买入持有基准** 对比

回测规则（避免未来函数）：
- 第 i 日收盘后用「截至第 i 日」的数据算综合评分
- 据此买/卖在**第 i+1 日开盘价**成交
- 每笔交易扣 **0.1%** 成本（手续费 + 滑点）
- 综合评分 ≥ 50 买入，≤ 25 清仓
- 综合评分 = 均线 + 动量加权（价值策略依赖实时基本面，无历史序列，不参与回测）

---

## 配置

### 美股 API Key（可选）
美股数据走 Alpha Vantage，免费额度 25 次/天。设置自己的 Key：

```bat
set ALPHA_VANTAGE_KEY=你的key
```

不设置则用 `demo`（额度极低，仅供试跑；美股建议自备 Key 或依赖 yfinance 备胎）。

### 本地缓存
行情数据自动缓存到 `.cache/`（默认 6 小时有效），重复查询同一股票不再重复联网，
省 API 额度也更快。删除 `.cache/` 目录即可强制刷新。

---

## 支持的股票代码格式

| 市场 | 示例代码 |
|------|---------|
| 美股 | `AAPL` `NVDA` `GOOG` `TSLA` |
| A股 | `600519` `000001` `300750`（需 VPN + 安装 akshare） |
| 港股 | `00700` `09992` `00100` `02388` |

---

## 目录结构

```
古牛量化/
├── app.py               # Flask 后端（/api/analyze、/api/backtest）
├── backtest.py          # 回测引擎（新增）
├── data_fetcher.py      # 数据获取层 + 本地缓存
├── requirements.txt
├── start.bat            # Windows 启动脚本（新增）
├── start.sh             # macOS / Linux 启动脚本
├── strategies/
│   ├── strategy_ma.py          # 均线金叉（add_indicators + score_at + run）
│   ├── strategy_value.py       # 低估值价值
│   └── strategy_momentum.py    # 动量反转（add_indicators + score_at + run）
└── templates/
    └── index.html
```

---

## 注意事项

- 数据来源为腾讯财经 / Alpha Vantage / yfinance / akshare，可能存在延迟
- **本工具仅供辅助参考，不构成投资建议。回测基于历史，不代表未来表现。**
- 这几个策略较简单，回测中常跑输买入持有（但回撤通常更小）——这正是诚实回测应当呈现的结果
- 实盘前请用更长区间、多只标的充分验证
