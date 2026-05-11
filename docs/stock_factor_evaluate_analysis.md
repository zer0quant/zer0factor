# stock_factor_evaluate 因子评估流程分析

> 来源：`/data/notebooks/admin/project/stock_factor_evaluate`  
> 分析日期：2026-04-30

---

## 项目结构

```
stock_factor_evaluate/
├── functions/
│   ├── factor_evaluate.py   # 主流程：Single_Factor_Evaluate_Alens 类
│   ├── performance.py       # 性能计算：IC、分组收益率、换手率
│   ├── utils_fe.py          # 工具函数：收益率计算、股票池整理
│   ├── factor_corr.py       # 因子相关系数计算
│   └── plotting.py          # 可视化
└── run_evaluate/
    ├── run_evaluate_01.ipynb  # 单因子评估入口
    ├── run_ft_corr.ipynb      # 因子相关系数入口
    └── run_summary_01.ipynb   # 汇总报告入口
```

---

## 整体评估流程

```
初始化参数
    │
    ▼
加载基础数据 (load_basic_data_ddb)
    │── 股票收益率矩阵 (DDB)
    │── 未来 N 期收益率 (forward returns)
    │── 多股票池数据 (hs300 / zz500 / zz1000 等)
    │── 指数K线 → 指数未来收益率
    │
    ▼
循环每个因子 × 中性化类型 × 股票池
    │
    ├── 1. 因子数据加载 & 对齐
    ├── 2. 缺失率 / 覆盖率统计
    ├── 3. 因子分组 (quantize)
    ├── 4. 截面超额收益率 (demean)
    │
    ├── IC 分析模块
    │       ├── 每日 Rank IC 序列
    │       ├── 因子方向判断
    │       ├── IC 统计 (mean / std / ICIR)
    │       ├── IC 分频率统计 (日 / 周 / 月)
    │       ├── IC 胜率
    │       └── 近期 IC 衰减比
    │
    ├── 收益率分析模块
    │       ├── 分组平均收益率 (多周期归一化)
    │       ├── 多 / 空 / 多空组收益率
    │       ├── 相对指数超额收益率
    │       ├── 因子值加权全市场收益率
    │       └── 收益率评价指标 (CAGR / 夏普 / 卡玛 / 最大回撤)
    │
    ├── 换手率模块
    │       ├── 多头组逐日换手率
    │       ├── 空头组逐日换手率
    │       └── 年化单边换手率
    │
    └── 单调性模块
            ├── 分组收益率单调性 (Spearman 与分组号的秩相关)
            └── 分时段单调性统计 (均值 / IR / >0% 占比 / >50% 占比)
    │
    ▼
汇总评价指标 DataFrame (df_ev_all)
    │
    ▼
可视化 & 结果保存
```

---

## 各模块详解

### 1. 初始化参数 (`Single_Factor_Evaluate_Alens.__init__`)

| 参数 | 说明 | 默认值 |
|---|---|---|
| `test_name` | 本次测试名称 | — |
| `universe_list` | 股票池列表 | `['mv70p', 'zz1800']` |
| `trade_p` | 调仓频率 | `'1d'` |
| `stg_dt1 / stg_dt2` | 测试起止时间 | — |
| `num_groups` | 分组数量 | `10` |
| `period_list` | 预测周期 | `['next_1', 'next_3', 'next_5']` |
| `price_type` | 收益率价格类型 | `'open'` |

支持的股票池：`all_trade` / `zzall` / `hs300` / `zz500` / `zz1000` / `zz1800` / `zz3800` / `mv2000` ~ `mv3000` / `mv50p` ~ `mv90p`

---

### 2. 基础数据加载 (`load_basic_data_ddb`)

```
DDB 数据源
    │
    ├── 股票日频收益率 (ret_open / ret_close / ret_twap15m)
    │       └─→ pivot 为 [datetime × symbol] 矩阵
    │
    ├── compute_forward_returns()
    │       ├── 去极值 (±20%)
    │       ├── 净值累乘后 pct_change(N)
    │       └── shift(-N) 得未来 N 期收益率
    │           → 输出双重索引 DataFrame (datetime, symbol)
    │
    ├── 股票池数据 (每日每池子的成分股列表)
    │       └─→ generate_multi_universe_df()
    │           → explode 展开为双重索引 bool 列
    │
    ├── 合并未来收益率 + 股票池标记
    │
    └── 指数K线 → compute_index_returns()
            → df_index_ret_next (shift(-1) 得下一日指数收益率)
```

---

### 3. IC 分析模块 (`performance.py`)

#### 3.1 每日 Rank IC
- 每个截面日期，对 `factor` 与 `next_N` 做 **Spearman 秩相关**
- 输出：`df_daily_ic`，index 为 datetime，列为各预测周期

#### 3.2 因子方向
- `sum(IC) > 0` → 方向为 +1（因子值越大，未来收益越高）
- `sum(IC) < 0` → 方向为 -1
- 可通过 `direction` 参数强制指定

#### 3.3 IC 统计指标

| 指标 | 计算方式 |
|---|---|
| IC_mean | 时序均值 |
| IC_std | 时序标准差 |
| ICIR | IC_mean / IC_std |
| IC 胜率 | IC ≥ 0 的占比 |
| 近期 IC 衰减比 | 近期 20% IC 均值 / 全期 IC 均值 |

统计粒度：全期 / 日频 / 周频 / 月频

---

### 4. 收益率分析模块 (`performance.py`)

#### 4.1 分组收益率 (`mean_return_by_quantile`)
- 按 `factor_quantile × datetime` 分组，对各预测周期计算均值 & 标准误
- **多周期归一化**：将 next_N 的收益率统一折算到 next_1 量纲（复利换算）

#### 4.2 多空收益率
- `q_long`：IC 正向时取最高分组，负向时取最低分组
- `q_short`：相反
- 多空收益率 = `(ret_long - ret_short) / 2`（空头占用仓位）

#### 4.3 超额收益率（相对指数）
- 多头组收益率 − 对应指数未来收益率

#### 4.4 全市场因子加权收益率 (`calculate_factor_returns_full`)
- 权重 = 截面内各股票因子值归一化（去均值后按绝对值之和归一化）
- 净敞口为 0（多空平衡），多头权重 = 空头权重 = 0.5
- 同样进行多周期归一化

#### 4.5 收益率评价指标 (`cal_return_evaluate`)

| 指标 | 含义 |
|---|---|
| 总收益率 | 期末净值 − 1 |
| 年化复合收益率 (CAGR) | 净值 ^ (1/年数) − 1 |
| 最大回撤 | 净值 / 历史最大净值的最低点 |
| 卡玛比率 | CAGR / \|最大回撤\| |
| 夏普比率 | 年化均值 / 年化标准差 |

---

### 5. 换手率模块 (`performance.py`)

- 计算每日 `q_long` / `q_short` 两组的**单边换手率**
- 公式：`新买入股票数 / 持仓总股票数`
- 按预测周期 N 修正量纲（除以 N，折算到单日粒度）
- 输出年化单边换手率

---

### 6. 单调性模块 (`performance.py`)

- 计算各预测周期下，**分组编号与分组年化收益率**的 Spearman 相关系数
- 相关系数 × 因子方向 → 正值代表单调性良好
- 分时段（季度）统计：均值 / IR / >0% 占比 / >50% 占比

---

### 7. 因子相关系数 (`factor_corr.py`)

- 每年随机抽取 N 天的截面数据（抽取天数随年份递增）
- 将多个因子的截面数据纵向拼接，计算 **Pearson 相关系数矩阵**
- 去除对角线后输出 CSV
- 用于检测因子间的冗余性

---

## 关键数据结构

| 变量 | 类型 | 描述 |
|---|---|---|
| `df_basic` | MultiIndex DataFrame | 双重索引 (datetime, symbol)，含未来收益率 + 股票池标记 |
| `df_com` | MultiIndex DataFrame | 单因子 + 特定股票池的完整数据 |
| `df_daily_ic` | DataFrame | index=datetime，列=next_N |
| `mean_quant_ret_bydate` | MultiIndex DataFrame | 双重索引 (factor_quantile, datetime) |
| `df_ev_all` | DataFrame | 所有因子 × 股票池 × 预测周期的汇总评价指标 |

---

## 因子中性化类型

| 后缀 | 含义 |
|---|---|
| `@std` | 标准化 |
| `@ind` | 行业中性化 |
| `@mv` | 市值中性化 |
| `@im` | 行业 + 市值中性化 |

---

## 对 zer0factor 的启示

| stock_factor_evaluate 能力 | zer0factor 对应模块 | 现状 |
|---|---|---|
| 未来收益率计算 | `zer0factor/eval/` | 空 |
| IC / ICIR 分析 | `zer0factor/eval/` | 空 |
| 分组收益率 / 单调性 | `zer0factor/eval/` | 空 |
| 换手率分析 | `zer0factor/eval/` | 空 |
| 多空组合收益率 | `zer0factor/portfolio/` | 空 |
| 因子相关系数 | `zer0factor/factor/` | 空 |
| 因子数据存储 | `zer0factor/storage.py` | **已实现** |
| 配置管理 | `zer0factor/config.py` | **已实现** |
