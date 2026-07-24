/**
 * AlphaOS 金融术语词库
 *
 * 用法:
 *   highlightTerms(text)       → 将匹配术语替换为彩色带解释的 HTML
 *   highlightInDOM(container)  → 遍历已有的 DOM 子树,对文本节点进行高亮
 */
(function () {
  "use strict";

  const GLOSSARY = [
    /* ---- 估值指标 ---- */
    {
      term: "市盈率",
      color: "var(--amber)",
      explanation:
        "市盈率（P/E）= 股价 ÷ 每股收益，反映市场愿意为每 1 元利润支付的价格。数值越高代表市场对增长预期越高，但也意味着估值更贵。同行业对比更有意义。",
    },
    {
      term: "市净率",
      color: "var(--amber)",
      explanation:
        "市净率（P/B）= 股价 ÷ 每股净资产，衡量股价相对于公司账面价值的倍数。<1 可能被低估，但也可能反映资产质量有问题。银行、保险等重资产行业常用。",
    },
    {
      term: "市销率",
      color: "var(--amber)",
      explanation:
        "市销率（P/S）= 市值 ÷ 营业收入，适用于尚未盈利的成长型公司。越低说明市场为每元收入支付的价格越低，但不能直接反映盈利能力。",
    },
    {
      term: "PEG",
      color: "var(--amber)",
      explanation:
        "PEG = 市盈率 ÷ 盈利增长率，修正了高增长公司的 PE 虚高问题。PEG < 1 常被视为低估，但增长率预测本身有不确定性。",
    },
    {
      term: "股息率",
      color: "var(--accent-strong)",
      explanation:
        "股息率 = 每股股息 ÷ 股价，衡量持有股票获得的分红回报率。通常 3-5% 算较高，但高股息可能伴随股价下跌或分红不可持续。",
    },
    {
      term: "每股收益",
      color: "var(--accent-strong)",
      explanation:
        "EPS（Earnings Per Share）= 净利润 ÷ 总股本，代表每股股票享有的利润。是计算 PE 的基础指标，也是市场关注的核心盈利指标。",
    },
    {
      term: "每股净资产",
      color: "var(--accent-strong)",
      explanation:
        "每股净资产 = 股东权益 ÷ 总股本，代表每股股票对应的账面资产价值。是市净率计算的依据，也是衡量公司清算价值的重要参考。",
    },
    {
      term: "自由现金流",
      color: "var(--accent-strong)",
      explanation:
        "自由现金流（FCF）= 经营现金流 − 资本支出，公司真正「自由」可支配的钱。比净利润更真实，因为净利润含非现金项目。持续正 FCF 是健康公司的标志。",
    },

    /* ---- 盈利能力指标 ---- */
    {
      term: "净资产收益率",
      color: "var(--blue)",
      explanation:
        "ROE（Return on Equity）= 净利润 ÷ 股东权益，衡量公司用股东的钱赚了多少钱。长期 >15% 通常算优秀，但要结合杠杆率看——高杠杆可能虚高 ROE。",
    },
    {
      term: "总资产收益率",
      color: "var(--blue)",
      explanation:
        "ROA（Return on Assets）= 净利润 ÷ 总资产，衡量公司利用全部资产的效率。不受资本结构影响，适合跨行业比较盈利能力的基准。",
    },
    {
      term: "毛利率",
      color: "var(--blue)",
      explanation:
        "毛利率 = (营收 − 营业成本) ÷ 营收，反映产品或服务本身的盈利空间。高毛利率通常意味着品牌溢价或技术壁垒（如茅台 >90%，软件 >70%）。",
    },
    {
      term: "净利率",
      color: "var(--blue)",
      explanation:
        "净利率 = 净利润 ÷ 营收，扣掉所有费用后真正赚到的比例。反映综合管理效率，不同行业差异大（零售 ~2%，高端制造 ~10%）。",
    },
    {
      term: "EBIT",
      color: "var(--blue)",
      explanation:
        "息税前利润（Earnings Before Interest & Tax），剔除资本结构和税率差异后的经营利润。常用于跨公司比较经营能力，也是企业价值倍数（EV/EBIT）的基础。",
    },
    {
      term: "EBITDA",
      color: "var(--blue)",
      explanation:
        "税息折旧及摊销前利润 = EBIT + 折旧 + 摊销，近似衡量公司经营产生的现金流。常用于评估重资产行业（钢铁、电信）的现金生成能力。",
    },

    /* ---- 成长性指标 ---- */
    {
      term: "同比增长",
      color: "var(--accent-strong)",
      explanation:
        "同比 = 本期数据 ÷ 去年同期 − 1，消除季节因素影响，反映业务的真实增长趋势。优于环比，是财报分析中最常用的增长口径。",
    },
    {
      term: "环比增长",
      color: "var(--accent-strong)",
      explanation:
        "环比 = 本期数据 ÷ 上期数据 − 1，反映短期变化趋势，但受季节因素影响大。适合跟踪季度之间的边际变化。",
    },
    {
      term: "复合年增长率",
      color: "var(--accent-strong)",
      explanation:
        "CAGR（Compound Annual Growth Rate）= (期末值/期初值)^(1/n) − 1，n 年间的年均增长率。平滑了中间波动，是衡量长期增长的标准方式。",
    },

    /* ---- 量化 / 风险指标 ---- */
    {
      term: "夏普比率",
      color: "var(--amber)",
      explanation:
        "夏普比率 = (收益率 - 无风险利率) ÷ 波动率，衡量每承担 1 单位风险获得了多少超额回报。>1 算不错，>2 很好，>3 极优秀。是基金/策略评价的黄金标准。",
    },
    {
      term: "最大回撤",
      color: "var(--red)",
      explanation:
        "最大回撤（Max Drawdown）= 从历史最高点到最低点的最大跌幅百分比。控制回撤比追求收益更重要——跌 50% 需要涨 100% 才能回本。",
    },
    {
      term: "Alpha",
      color: "var(--blue)",
      explanation:
        "Alpha（α）= 实际收益 − 预期收益（基于 Beta 的 CAPM 模型），衡量投资组合的超额收益。正 Alpha 表示跑赢了风险模型给出的基准，是基金经理能力的核心体现。",
    },
    {
      term: "Beta",
      color: "var(--blue)",
      explanation:
        "Beta（β）衡量个股相对于大盘的波动敏感度。β=1 与大盘同步，β>1 波动更大（如券商股 ~1.5），β<1 更抗跌（如公用事业 ~0.5）。",
    },
    {
      term: "波动率",
      color: "var(--amber)",
      explanation:
        "波动率衡量价格在单位时间内波动的幅度，通常用收益率的标准差表示。年化波动率 20% 意味单日涨跌 1σ 约 ±1.26%。波动 ≠ 风险，但常被作为风险的代理指标。",
    },
    {
      term: "年化波动率",
      color: "var(--amber)",
      explanation:
        "将日/周波动率换算到年度的标准化度量，方便跨资产比较。A 股个股年化波动率通常在 25-50%，美股 ~20-35%。",
    },
    {
      term: "信息比率",
      color: "var(--blue)",
      explanation:
        "IR（Information Ratio）= (组合收益 − 基准收益) ÷ 跟踪误差，衡量主动管理能力。IR > 0.5 算好，>1 非常优秀。与夏普的核心区别：夏普对比无风险利率，IR 对比基准。",
    },
    {
      term: "跟踪误差",
      color: "var(--blue)",
      explanation:
        "跟踪误差衡量投资组合收益与基准指数收益之间的偏离程度（标准差）。被动基金希望跟踪误差尽量小，主动基金则用跟踪误差换取 Alpha。",
    },
    {
      term: "在险价值",
      color: "var(--red)",
      explanation:
        "VaR（Value at Risk）= 在给定置信水平（通常 95% 或 99%）下、一定持有期内可能的最大损失。如日 95% VaR = -2% 意味着每天只有 5% 概率亏损超过 2%。不覆盖尾部极端风险。",
    },

    /* ---- 技术分析 ---- */
    {
      term: "均线",
      color: "var(--accent-strong)",
      explanation:
        "移动平均线（MA）平滑价格走势，消除噪音。常用：MA5（周线）、MA20（月线）、MA60（季线）、MA250（年线）。金叉（短线上穿长线）看涨，死叉看跌。",
    },
    {
      term: "MACD",
      color: "var(--accent-strong)",
      explanation:
        "指数平滑异同移动平均线，由快线（EMA12）- 慢线（EMA26）的差值和信号线组成。金叉/死叉和柱状图背离是核心用法。适合趋势行情，震荡市中易失效。",
    },
    {
      term: "RSI",
      color: "var(--accent-strong)",
      explanation:
        "相对强弱指标（Relative Strength Index），0-100，衡量近期涨跌幅的比值。>70 超买（可能回调），<30 超卖（可能反弹）。极端值在趋势行情中可能长期钝化。",
    },
    {
      term: "布林带",
      color: "var(--accent-strong)",
      explanation:
        "布林带由中轨（MA20）、上下轨（±2σ 标准差）组成。带宽反映波动性，价格触碰上下轨可能预示反转或趋势加速。带宽极度收缩（开口变窄）后往往是爆发前兆。",
    },
    {
      term: "成交量",
      color: "var(--amber)",
      explanation:
        "成交量是一定时间内的交易股数/金额，反映市场活跃度和参与度。价升量增 = 健康上涨，价升量缩 = 动能不足，放量下跌 = 恐慌或主力出货。",
    },
    {
      term: "换手率",
      color: "var(--amber)",
      explanation:
        "换手率 = 成交量 ÷ 流通股数，反映股票的交易活跃度。高换手（>10%）意味着分歧大或短线博弈，低换手意味着筹码稳定。新股通常换手率极高。",
    },
    {
      term: "K线",
      color: "var(--accent-strong)",
      explanation:
        "K线（蜡烛图）展示开盘价、收盘价、最高价、最低价四个信息。阳线（收盘>开盘）用红/绿色系表示，阴线（收盘<开盘）用绿/蓝色系。单根 K 线 + 组合形态是技术分析的语言基础。",
    },
    {
      term: "成交量加权平均价格",
      color: "var(--accent-strong)",
      explanation:
        "VWAP = 成交金额 ÷ 成交量，全天交易的平均成交价。机构常用 VWAP 评估交易执行质量，高于 VWAP 说明买入均价偏高，低于则说明执行较好。",
    },

    /* ---- 选股因子 ---- */
    {
      term: "市值",
      color: "var(--amber)",
      explanation:
        "市值 = 股价 × 总股本，公司的市场总价值。通常分大盘（>500亿）、中盘（100-500亿）、小盘（<100亿）。市值大小与预期收益、波动率有一定关联。",
    },
    {
      term: "流通市值",
      color: "var(--amber)",
      explanation:
        "流通市值 = 股价 × 流通股数，只计算可在二级市场自由交易的股份部分。解禁前后流通市值大幅变化，可能带来股价波动。",
    },
    {
      term: "动量因子",
      color: "var(--accent-strong)",
      explanation:
        "动量因子：过去涨的股票未来一段时间倾向于继续涨（趋势延续），但 A 股短周期反转效应强于动量。最常见的量化因子之一，通常用过去 6-12 个月收益率衡量。",
    },
    {
      term: "价值因子",
      color: "var(--accent-strong)",
      explanation:
        "价值因子：低 PE、低 PB、高股息率的股票倾向于长期跑赢市场。核心逻辑是市场对利空过度反应，估值偏低蕴含安全边际。Fama-French 三因子模型的核心因子之一。",
    },
    {
      term: "质量因子",
      color: "var(--accent-strong)",
      explanation:
        "质量因子：高 ROE、低杠杆、盈利稳定的公司倾向于获得超额收益。逻辑是好公司本身就有溢价，且在下跌中更抗跌。近几年 A 股质量因子表现较优。",
    },
    {
      term: "低波因子",
      color: "var(--accent-strong)",
      explanation:
        "低波因子：历史上波动率较低的股票长期回报反而高于高波动股票（低波动异象）。逻辑是高波动吸引投机推高价格但后续收益低，低波动由于关注不足被折价。",
    },
    {
      term: "规模因子",
      color: "var(--accent-strong)",
      explanation:
        "规模因子（市值因子）：小盘股长期跑赢大盘股。Fama-French 三因子的核心组成，在 A 股历史上效果显著。但小盘股流动性差、波动大、有壳价值干扰。",
    },
    {
      term: "因子暴露",
      color: "var(--amber)",
      explanation:
        "因子暴露（因子载荷）衡量某只股票或组合对一个因子的敏感度。暴露度越高，该因子的涨跌对组合影响越大。多因子模型通过组合不同因子暴露实现分散化。",
    },
    {
      term: "因子拥挤",
      color: "var(--red)",
      explanation:
        "因子拥挤：大量资金涌入同一个因子导致策略失效或出现踩踏的风险。拥挤的因子往往夏普比率骤降、相关性上升，是因子投资最大的隐性风险之一。",
    },

    /* ---- 交易策略 ---- */
    {
      term: "回测",
      color: "var(--amber)",
      explanation:
        "回测是利用历史数据模拟量化策略表现的过程。核心陷阱：前视偏差、幸存者偏差、过拟合、交易成本忽略。回测好 ≠ 实盘好，但它是不好策略的必要条件。",
    },
    {
      term: "过拟合",
      color: "var(--red)",
      explanation:
        "过拟合是策略在历史数据上表现极好但在新数据上失效。常见症状：参数过于精细、策略在样本外收益断崖式下跌。避免方法包括交叉验证、简化参数、引入正则化。",
    },
    {
      term: "前视偏差",
      color: "var(--red)",
      explanation:
        "前视偏差（未来数据泄漏）是回测中不小心使用了未来信息。例如「用财报发布后的数据去模拟财报发布前的交易」，是最常见的回测错误。",
    },
    {
      term: "幸存者偏差",
      color: "var(--red)",
      explanation:
        "幸存者偏差指回测时只用了现存的股票而忽略了已被退市/摘牌的公司。这会高估历史收益。回测应使用对应时点的全部股票池，包括后来退市的。",
    },
    {
      term: "多因子模型",
      color: "var(--accent-strong)",
      explanation:
        "多因子模型用多个因子（如价值、动量、质量、低波）的线性组合来解释和预测股票收益。Fama-French 三因子是代表，后续扩展到五因子甚至上百因子。核心是因子选择、权重分配和风险控制。",
    },
    {
      term: "统计套利",
      color: "var(--accent-strong)",
      explanation:
        "统计套利（Stat Arb）利用统计模型识别相关资产间的定价偏差，当偏差超过阈值时建立多空头寸，等待均值回归获利。典型是配对交易。不是无风险套利，存在模型风险。",
    },
    {
      term: "配对交易",
      color: "var(--accent-strong)",
      explanation:
        "配对交易（Pairs Trading）= 找到两只高度相关的股票，做多弱势的做空强势的，赌价差回归均值。市场中性策略，理论上不受大盘涨跌影响。核心是价差序列的平稳性。",
    },
    {
      term: "量化宽松",
      color: "var(--amber)",
      explanation:
        "QE（Quantitative Easing）= 央行直接购买国债等资产向市场注入流动性。不是「印钱」那么简单——本质是通过改变资产持有结构压低长端利率、推动资金流向实体经济。退出不当可能引发市场震荡。",
    },
    {
      term: "对冲",
      color: "var(--amber)",
      explanation:
        "对冲是通过持有相反方向的资产来降低风险。如持有股票现货同时做空股指期货。对冲降低波动的同时也会限制上行空间，纯粹的对冲策略往往收益不高。",
    },

    /* ---- 市场结构 ---- */
    {
      term: "A股",
      color: "var(--accent-strong)",
      explanation:
        "A 股是在上海/深圳交易所上市、以人民币计价、供境内投资者（及部分外资通过沪深港通）交易的股票。是反映中国经济的核心市场，以散户为主、波动较大。",
    },
    {
      term: "创业板",
      color: "var(--accent-strong)",
      explanation:
        "创业板（深交所，300/301 开头），面向成长型创新创业企业。门槛低于主板、涨跌幅 ±20%。高成长性与高波动性并存，行业集中在 TMT、医药。",
    },
    {
      term: "科创板",
      color: "var(--accent-strong)",
      explanation:
        "科创板（上交所，688 开头），服务国家战略新兴产业的硬科技公司。上市标准灵活（允许未盈利），涨跌幅 ±20%，机构参与比例高于主板。",
    },
    {
      term: "北交所",
      color: "var(--accent-strong)",
      explanation:
        "北交所（8 开头）服务于创新型中小企业，特别是「专精特新」。公司体量通常较小，流动性弱于沪深市场。上市门槛更低，退市也更灵活。",
    },
    {
      term: "沪深港通",
      color: "var(--accent-strong)",
      explanation:
        "沪深港通（陆股通）是境外资金投资 A 股的通道。北向资金 = 香港流入 A 股，南向资金 = 内地流入港股。北向资金动向常被作为「聪明钱」的信号。",
    },
    {
      term: "融资融券",
      color: "var(--amber)",
      explanation:
        "融资（做多）= 借入资金买入股票，杠杆放大收益和亏损。融券（做空）= 借入股票卖出后买回还券。两融余额反映投资者风险偏好，是重要的市场情绪指标。",
    },
    {
      term: "股权风险溢价",
      color: "var(--amber)",
      explanation:
        "ERP（Equity Risk Premium）= 股票预期收益率 − 无风险利率，衡量投资者承担股权风险要求的额外回报。ERP 越高说明股票相对债券越便宜，是判断市场底部区间的参考指标之一。",
    },

    /* ---- 组合与风险 ---- */
    {
      term: "相关性",
      color: "var(--accent-strong)",
      explanation:
        "相关性（Correlation）衡量两个资产走势的同步程度，值域 [-1, 1]。0.8 以上高度正相关，-0.5 以下负相关。低相关资产组合可有效降低整体波动而不牺牲太多收益。",
    },
    {
      term: "协整",
      color: "var(--accent-strong)",
      explanation:
        "协整（Cointegration）衡量两个时间序列是否保持长期均衡关系。即使相关性低，两只股票也可能协整——它们各自可以随意游走，但相互的价差具有均值回复特性。配对交易立足的理论基础。",
    },
    {
      term: "正态分布",
      color: "var(--accent-strong)",
      explanation:
        "正态分布在金融中常用于假设收益率分布，但实际数据是「肥尾」的——极端事件发生概率远高于正态模型预测。这是 Black-Scholes 等经典模型的局限，也是风险管理必须考虑尾部风险的原因。",
    },
    {
      term: "肥尾",
      color: "var(--red)",
      explanation:
        "肥尾（Fat Tail）指收益分布两端极端值的概率大于正态分布预测。金融市场的典型特征：你以为「百年一遇」的金融危机可能每十年就来一次。处理肥尾需要做压力测试而非依赖标准差。",
    },
    {
      term: "黑天鹅",
      color: "var(--red)",
      explanation:
        "黑天鹅事件是不可预测的、影响巨大的稀有事件。发生后人们倾向于「事后解释」（事后归因偏差）。投资中应对黑天鹅不是预测它，而是保持仓位弹性 + 尾部对冲。",
    },
    {
      term: "分散化",
      color: "var(--accent-strong)",
      explanation:
        "分散化（Diversification）是唯一免费的午餐——通过持有不同资产降低组合波动而不必然降低收益。关键是底层资产间的低相关性。但多资产也有尾部相关性上升的问题。",
    },

    /* ---- 行为金融 ---- */
    {
      term: "锚定效应",
      color: "var(--amber)",
      explanation:
        "锚定效应：投资者过度依赖最初获得的信息（锚点）做决策。如看到 100 元的股票跌到 60 元觉得「便宜」，但其实合理价值可能是 40 元。识别锚定是逆向投资的起点。",
    },
    {
      term: "处置效应",
      color: "var(--amber)",
      explanation:
        "处置效应：投资者倾向于过早卖出盈利的股票（落袋为安）而长期持有亏损的股票（等回本）。行为上错误地以买入价而非当前价值作为决策参考，是散户最常见的行为偏误。",
    },
    {
      term: "确认偏误",
      color: "var(--amber)",
      explanation:
        "确认偏误：人们倾向于寻找和分析支持自己已有观点的信息，忽略相反证据。在投资中表现为「看多时只找利多消息」，是导致死扛和加仓错误的核心心理陷阱。",
    },
    {
      term: "羊群效应",
      color: "var(--amber)",
      explanation:
        "羊群效应（Herd Behavior）：投资者忽视自己判断而跟随多数人的行为。追涨杀跌是典型——高点被乐观情绪吸引买入，低点在恐慌中割肉。机构也免不了，因为「和别人一起错」比「自己一个人错」的心理成本更低。",
    },

    /* ---- 进阶量化 ---- */
    {
      term: "Alpha 衰减",
      color: "var(--red)",
      explanation:
        "Alpha 衰减指一个有效的策略随着时间推移超额收益逐渐降低直至消失。原因包括市场效率提升、因子拥挤、策略被同行复制。是量化投资面临的永恒挑战——必须持续迭代创新。",
    },
    {
      term: "策略容量",
      color: "var(--amber)",
      explanation:
        "策略容量指在不显著影响收益的前提下策略能管理的最大资金量。高夏普、低换手的策略往往容量更大。高频策略容量极小（几亿到几十亿），而基本面因子可容纳百亿以上。",
    },
    {
      term: "滑点",
      color: "var(--amber)",
      explanation:
        "滑点（Slippage）= 预期成交价与实际成交价的差异，主要由流动性不足和市场冲击造成。回测中不考虑滑点会严重高估收益，尤其对小市值、高换手策略影响巨大。",
    },
    {
      term: "市场冲击",
      color: "var(--amber)",
      explanation:
        "市场冲击是大额交易时自身对价格的推高或压低效应。买 100 万和买 1 个亿的平均成交价差异巨大。算法交易的核心任务之一就是在冲击和执行速度之间找到最优平衡。",
    },
    {
      term: "T+1",
      color: "var(--accent-strong)",
      explanation:
        "A 股的 T+1 制度：当天买入的股票最快第二天才能卖出。限制了日内交易策略的实现，也对高频交易形成天然壁垒。但结合底仓仍可实现日内「变相 T+0」。",
    },
    {
      term: "涨跌停",
      color: "var(--accent-strong)",
      explanation:
        "涨跌停板制度限制单日最大涨跌幅：主板 ±10%，创业板/科创板 ±20%，北交所 ±30%。旨在防止过度波动，但也会造成流动性枯竭（跌停时无法卖出）和磁吸效应（越靠近停板越加速）。",
    },
  ];

  /* 按词条长度从长到短排序，避免短词抢在长词之前匹配 */
  const SORTED = GLOSSARY.slice().sort((a, b) => b.term.length - a.term.length);

  /* 构建正则 —— 只匹配完整词（非汉字/字母中间被拆分） */
  const ESCAPED_TERMS = SORTED.map((g) =>
    g.term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  );
  const RE = new RegExp(`(^|[^\\p{L}])(${ESCAPED_TERMS.join("|")})([^\\p{L}]|$)`, "giu");

  /**
   * 查词条对象（用原始未转译的词条名查找）
   */
  function lookup(term) {
    return SORTED.find((g) => g.term.toLowerCase() === term.toLowerCase());
  }

  /**
   * highlightTerms(text) → 高亮后的 HTML 字符串
   *
   * 将纯文本中的词汇替换为带颜色 + data-explanation 的 <span>
   */
  function highlightTerms(text) {
    const safe = String(text)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");

    return safe.replace(RE, (match, before, term, after) => {
      const entry = lookup(term);
      if (!entry) return match;
      return (before || "") +
        `<span class="glossary-term" style="color:${entry.color}"` +
        ` data-explanation="${entry.explanation
          .replaceAll("&", "&amp;")
          .replaceAll('"', "&quot;")}">${term}</span>` +
        (after || "");
    });
  }

  /**
   * highlightInDOM(root) → undefined
   *
   * 遍历 DOM 树中的所有文本节点，将其文本用高亮 HTML 替换。
   * 只处理 visible 文本节点。
   */
  function highlightInDOM(root) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null, false);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);

    for (const node of nodes) {
      // 跳过已有高亮标记（避免重复处理）
      if (node.parentElement && node.parentElement.closest(".glossary-term")) continue;

      const html = highlightTerms(node.textContent);
      if (html === node.textContent) continue; // 没有命中任何词

      const span = document.createElement("span");
      span.innerHTML = html;
      node.parentNode.replaceChild(span, node);
    }
  }

  /* ---- 知识库持久化（localStorage） ---- */
  const KNOWLEDGE_KEY = "alphaos.glossary.knowledge";

  function getKnowledge() {
    try {
      return JSON.parse(localStorage.getItem(KNOWLEDGE_KEY)) || [];
    } catch { return []; }
  }

  function saveKnowledge(list) {
    try { localStorage.setItem(KNOWLEDGE_KEY, JSON.stringify(list)); } catch { /* noop */ }
  }

  function addKnowledge(term, color, explanation) {
    const list = getKnowledge();
    if (list.some((item) => item.term === term)) return false;
    list.push({ term, color, explanation, savedAt: Date.now() });
    saveKnowledge(list);
    return true;
  }

  function removeKnowledge(term) {
    saveKnowledge(getKnowledge().filter((item) => item.term !== term));
  }

  function isKnowledgeSaved(term) {
    return getKnowledge().some((item) => item.term === term);
  }

  /* 导出到全局 */
  const AlphaGlossary = {
    highlightTerms,
    highlightInDOM,
    lookup,
    getKnowledge,
    addKnowledge,
    removeKnowledge,
    isKnowledgeSaved,
  };
  if (typeof globalThis !== "undefined") globalThis.AlphaGlossary = AlphaGlossary;
})();
