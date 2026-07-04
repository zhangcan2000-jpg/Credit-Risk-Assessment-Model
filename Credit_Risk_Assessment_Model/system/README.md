# 农户信贷智能风险分层系统 V1.0

> 2026年"数据要素×"大赛山东分赛 - 现代农业赛道
> 青岛农商银行即墨支行

## 🚀 快速启动

### 方式1：双击启动（推荐）
```
双击 run.bat
```

### 方式2：命令行启动
```bash
cd D:\profile\数据要素\farm_credit_risk\system
streamlit run 🏠_首页.py
```

启动后浏览器自动打开 `http://localhost:8501`

## 📂 系统模块

| 模块 | 功能 |
|------|------|
| 🏠 **首页** | 系统概览、核心指标、风险分布 |
| 👤 **单户评估** | 输入农户信息，输出风险等级与差异化措施 |
| 📋 **批量评估** | CSV上传批量评估，自动生成报告 |
| 🚨 **风险监测** | 评估历史、风险分布统计、高风险预警 |

## 🔧 系统依赖

```bash
pip install -r requirements.txt
```

核心依赖：
- streamlit (Web框架)
- lightgbm (机器学习模型)
- pandas (数据处理)
- plotly (交互式图表)

## 📊 模型性能

| 数据集 | AUC | KS | 说明 |
|--------|-----|-----|------|
| Home Credit 真实数据（30.7万） | 0.7916 | 0.4423 | 达到银行实战水平 |
| 涉农仿真数据（2万） | 0.9635 | 0.8024 | 验证涉农场景有效性 |

## 📁 目录结构

```
system/
├── 🏠_首页.py                          主入口（首页）
├── run.bat                         Windows 启动脚本
├── requirements.txt                依赖列表
├── README.md                       本文件
│
├── core/                           核心业务逻辑
│   ├── predictor.py                风险预测引擎
│   └── config.py                   系统配置
│
├── pages/                          页面模块
│   ├── 1_👤_单户评估.py
│   ├── 2_📋_批量评估.py
│   └── 3_🚨_风险监测.py
│
├── uploads/                        上传文件目录
└── history/                        评估历史记录
    ├── evaluations.json            单户评估历史
    └── batch_history.json          批量评估历史
```

## ⚠️ 启动前确认

确保以下文件已生成（运行根目录的脚本即可）：

```
farm_credit_risk/
├── models/farm_model.pkl           由 03b_train_farm_model.py 生成
├── output/farm_metrics.json        由 03b 生成
└── output/real_metrics.json        由 02b 生成
```

如果未生成，请先在项目根目录运行：
```bash
python 03_generate_farm_data.py    # 生成合成数据
python 03b_train_farm_model.py     # 训练农户模型
```

## 📞 技术支持

青岛农商银行即墨支行 · 普惠部
负责人：杨京泽
