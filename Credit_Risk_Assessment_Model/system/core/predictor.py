"""
核心业务逻辑层 - 农户信贷风险预测引擎
==========================================
封装模型加载、特征构造、风险预测、决策建议、因子解释等核心能力
供各业务页面调用
"""
import os
import sys

try:
    import io
    if hasattr(sys.stdout, 'buffer') and sys.stdout.buffer is not None:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
except (ValueError, AttributeError, io.UnsupportedOperation):
    pass

import json
import joblib
import numpy as np
import pandas as pd
from pathlib import Path

# 模型路径（兼容两种部署方式）
_HERE = Path(__file__).parent
_MODEL_PATHS = [
    _HERE.parent.parent / "models" / "farm_model.pkl",       # 项目根目录
    _HERE.parent / "farm_model.pkl",                         # system目录
    _HERE / "farm_model.pkl",                                # core目录
]


def find_model():
    for p in _MODEL_PATHS:
        if p.exists():
            return str(p)
    return None


# ===== 加载模型（懒加载 + 缓存）=====
_model_bundle = None


def get_model():
    global _model_bundle
    if _model_bundle is None:
        path = find_model()
        if path is None:
            raise FileNotFoundError(
                "未找到模型文件 farm_model.pkl，请先运行 03b_train_farm_model.py"
            )
        _model_bundle = joblib.load(path)
    return _model_bundle


# ===== 风险等级阈值 =====
RISK_THRESHOLDS = {
    "low": 0.20,
    "high": 0.50,
}

# ===== 硬性拒贷规则（"连三累六"，覆盖模型预测）=====
# 近两年连续逾期 ≥3 次 或 累计逾期 ≥6 次 → 直接拒贷
REJECT_CONSECUTIVE_THRESHOLD = 3
REJECT_CUMULATIVE_THRESHOLD = 6

# ===== 资产负债率约束（升级规则，不拒贷）=====
# (家庭总负债 + 本次申请贷款) / 家庭总资产 ≥ 70% → 至少升级为高风险
LTV_HIGH_RISK_THRESHOLD = 0.70
LTV_WARN_THRESHOLD = 0.50

# ===== 差异化措施建议 =====
DIFFERENTIATED_ACTIONS = {
    "低风险": {
        "summary": "优质客户 - 放心贷",
        "loan_strategy": "纯信用贷，无需担保",
        "rate_strategy": "利率较基准下浮10%",
        "amount_strategy": "额度上浮30%",
        "process_strategy": "T+1放款绿色通道，自动化审批",
        "monitor_strategy": "贷后季度回访",
        "color": "#28a745",
        "icon": "✅",
    },
    "中风险": {
        "summary": "标准客户 - 增信贷",
        "loan_strategy": "需担保增信或抵质押",
        "rate_strategy": "标准利率",
        "amount_strategy": "标准额度",
        "process_strategy": "分批放款，加强用途核查",
        "monitor_strategy": "动态月度监测，重点关注",
        "color": "#ffc107",
        "icon": "⚠️",
    },
    "高风险": {
        "summary": "风险客户 - 严格管控",
        "loan_strategy": "限额管理或拒贷",
        "rate_strategy": "如若放贷则上浮风险溢价",
        "amount_strategy": "压缩额度或拒贷",
        "process_strategy": "人工复核，加强审查",
        "monitor_strategy": "贷后密集监测，月度评估",
        "color": "#dc3545",
        "icon": "🚨",
    },
    "拒贷": {
        "summary": "触发硬性规则 - 直接拒贷",
        "loan_strategy": "拒贷（触发连三累六规则）",
        "rate_strategy": "不适用",
        "amount_strategy": "不予授信",
        "process_strategy": "进入灰名单，人工复核申诉路径",
        "monitor_strategy": "如已放款则立即介入催收、压降额度",
        "color": "#7a1f1f",
        "icon": "⛔",
    },
}


def assign_tier(prob):
    if prob < RISK_THRESHOLDS["low"]:
        return "低风险"
    elif prob < RISK_THRESHOLDS["high"]:
        return "中风险"
    else:
        return "高风险"


def check_reject_rules(input_dict):
    """检查是否触发连三累六硬性拒贷规则。返回 (是否拒贷, 触发原因列表)。"""
    reasons = []
    cumulative = int(input_dict.get("overdue_count_history") or 0)
    consecutive = int(input_dict.get("consecutive_overdue") or 0)
    if cumulative >= REJECT_CUMULATIVE_THRESHOLD:
        reasons.append(
            f"近两年累计逾期 {cumulative} 次（≥{REJECT_CUMULATIVE_THRESHOLD} 次触发拒贷）"
        )
    if consecutive >= REJECT_CONSECUTIVE_THRESHOLD:
        reasons.append(
            f"近两年连续逾期 {consecutive} 次（≥{REJECT_CONSECUTIVE_THRESHOLD} 次触发拒贷）"
        )
    return bool(reasons), reasons


def compute_ltv(input_dict):
    """计算资产负债率 LTV = (家庭总负债 + 本次申请贷款金额) / 家庭总资产。
    返回 None 表示数据不足（如总资产≤0 或未填写）。"""
    try:
        assets = float(input_dict.get("total_assets") or 0)
        liabilities = float(input_dict.get("total_liabilities") or 0)
        loan = float(input_dict.get("loan_amount") or 0)
    except (TypeError, ValueError):
        return None
    if assets <= 0:
        return None
    return (liabilities + loan) / assets


def get_actions(tier):
    return DIFFERENTIATED_ACTIONS[tier]


def build_features(input_dict):
    """根据用户输入构造特征（与训练时保持一致）"""
    crop_subsidy_rate = {"玉米": 80, "小麦": 110, "水稻": 150, "花生": 50, "蔬菜": 30, "果树": 40}

    data = {
        "age": int(input_dict["age"]),
        "gender": input_dict["gender"],
        "marital": input_dict["marital"],
        "education": input_dict["education"],
        "crop": input_dict["crop"],
        "true_area": float(input_dict["true_area"]),
        "reported_area": float(input_dict["reported_area"]),
        "subsidy_area": float(input_dict["subsidy_area"]),
        "area_diff_ratio": (float(input_dict["reported_area"]) - float(input_dict["subsidy_area"])) / (float(input_dict["subsidy_area"]) + 1),
        "subsidy_amount": float(input_dict["subsidy_area"]) * crop_subsidy_rate.get(input_dict["crop"], 80),
        "subsidy_stable": 1 if input_dict["subsidy_stable"] == "是" else 0,
        "is_drought_year": 1 if input_dict["is_drought_year"] == "是" else 0,
        "has_greenhouse": 1 if input_dict.get("has_greenhouse", "否") == "是" else 0,
        "weather_score": float(input_dict["weather_score"]),
        "price_change": float(input_dict["price_change"]),
        "true_income": float(input_dict["true_income"]),
        "reported_income": float(input_dict["reported_income"]),
        "income_diff_ratio": (float(input_dict["reported_income"]) - float(input_dict["true_income"])) / (float(input_dict["true_income"]) + 1),
        "loan_amount": float(input_dict["loan_amount"]),
        "loan_term": int(input_dict["loan_term"]),
        "interest_rate": 0.06,
        "has_other_loan": 1 if input_dict["has_other_loan"] == "是" else 0,
        "overdue_count_history": int(input_dict["overdue_count_history"]),
        "loan_income_ratio": float(input_dict["loan_amount"]) / (float(input_dict["true_income"]) + 1),
    }
    return data


def predict(input_dict):
    """
    输入农户信息字典，返回完整评估结果
    返回: {
        probability, tier, actions, risk_factors, features
    }
    """
    bundle = get_model()
    features_dict = build_features(input_dict)
    df = pd.DataFrame([features_dict])

    # 类别编码
    for c in bundle["cat_cols"]:
        df[c], _ = pd.factorize(df[c])

    # 保证列顺序
    df = df[bundle["features"]]

    # 预测
    prob = float(bundle["model"].predict(df)[0])
    tier = assign_tier(prob)
    actions = get_actions(tier)
    risk_factors = detect_risk_factors(features_dict)

    # 资产负债率约束：LTV ≥ 70% → 至少升级为高风险
    ltv = compute_ltv(input_dict)
    if ltv is not None and ltv >= LTV_HIGH_RISK_THRESHOLD and tier in ("低风险", "中风险"):
        tier = "高风险"
        actions = get_actions("高风险")
        risk_factors.insert(0, {
            "factor": "资产负债率超标",
            "value": f"{ltv:.0%}",
            "severity": "严重",
            "explanation": (
                f"(家庭总负债 {input_dict.get('total_liabilities') or 0:.0f} + "
                f"申请贷款 {input_dict.get('loan_amount') or 0:.0f}) / "
                f"家庭总资产 {input_dict.get('total_assets') or 0:.0f} = {ltv:.0%}，"
                f"已超过 {int(LTV_HIGH_RISK_THRESHOLD*100)}% 红线，本次评估升级为高风险。"
            ),
        })
    elif ltv is not None and ltv >= LTV_WARN_THRESHOLD:
        risk_factors.append({
            "factor": "资产负债率偏高",
            "value": f"{ltv:.0%}",
            "severity": "中等",
            "explanation": (
                f"当前 LTV {ltv:.0%}（介于 {int(LTV_WARN_THRESHOLD*100)}% 与 "
                f"{int(LTV_HIGH_RISK_THRESHOLD*100)}% 之间），偿债压力上升，建议关注。"
            ),
        })

    # 硬性规则覆盖：连三累六 → 直接拒贷（最高优先级）
    rejected, reject_reasons = check_reject_rules(input_dict)
    if rejected:
        tier = "拒贷"
        actions = get_actions("拒贷")
        risk_factors.insert(0, {
            "factor": "触发硬性拒贷规则",
            "value": "连三累六",
            "severity": "严重",
            "explanation": "；".join(reject_reasons) + "。该结论为业务规则覆盖，优先于模型预测。",
        })

    return {
        "probability": prob,
        "tier": tier,
        "actions": actions,
        "risk_factors": risk_factors,
        "features": features_dict,
        "reject_reasons": reject_reasons,
        "ltv": ltv,
    }


def detect_risk_factors(features):
    """识别关键风险因子（可解释性）"""
    factors = []

    if features["area_diff_ratio"] > 0.1:
        severity = "严重" if features["area_diff_ratio"] > 0.5 else ("中等" if features["area_diff_ratio"] > 0.3 else "轻微")
        factors.append({
            "factor": "自报面积与补贴面积差异",
            "value": f"+{features['area_diff_ratio']:.0%}",
            "severity": severity,
            "explanation": "农户自报种植面积大于补贴登记面积，存在虚报嫌疑",
        })

    if features["is_drought_year"]:
        factors.append({
            "factor": "当年气象灾害",
            "value": "是",
            "severity": "中等",
            "explanation": "当年遭遇气象灾害，预计影响农户经营收入",
        })

    if not features["subsidy_stable"]:
        factors.append({
            "factor": "补贴领取不稳定",
            "value": "是",
            "severity": "中等",
            "explanation": "补贴领取不连续，反映经营规范性不足",
        })

    if features["price_change"] < -0.10:
        factors.append({
            "factor": "农产品价格下跌",
            "value": f"{features['price_change']:.0%}",
            "severity": "中等" if features["price_change"] > -0.2 else "严重",
            "explanation": "农产品价格下跌直接影响农户销售收入",
        })

    if features["overdue_count_history"] > 0:
        factors.append({
            "factor": "历史逾期记录",
            "value": f"{features['overdue_count_history']}次",
            "severity": "严重" if features["overdue_count_history"] >= 3 else "中等",
            "explanation": "历史存在逾期记录，反映还款意愿或能力问题",
        })

    if features["loan_income_ratio"] > 0.5:
        factors.append({
            "factor": "贷款/收入比偏高",
            "value": f"{features['loan_income_ratio']:.2f}",
            "severity": "严重" if features["loan_income_ratio"] > 1 else "中等",
            "explanation": "贷款金额相对收入过高，偿债压力大",
        })

    if features["true_area"] < 10:
        factors.append({
            "factor": "种植规模偏小",
            "value": f"{features['true_area']:.1f}亩",
            "severity": "中等",
            "explanation": "种植规模偏小，抗风险能力相对较弱",
        })

    if features["age"] > 60:
        factors.append({
            "factor": "年龄偏大",
            "value": f"{features['age']}岁",
            "severity": "中等",
            "explanation": "借款人年龄偏大，需关注还款能力持续性",
        })

    if features["has_other_loan"]:
        factors.append({
            "factor": "存在其他贷款",
            "value": "是",
            "severity": "轻微",
            "explanation": "存在多头借贷，需综合评估负债情况",
        })

    if features["income_diff_ratio"] > 0.3:
        factors.append({
            "factor": "自报收入虚高",
            "value": f"+{features['income_diff_ratio']:.0%}",
            "severity": "严重" if features["income_diff_ratio"] > 0.8 else "中等",
            "explanation": "自报收入明显高于测算真实收入，存在夸大嫌疑",
        })

    return factors


def predict_batch(records):
    """批量预测，records 是字典列表"""
    bundle = get_model()
    crop_subsidy_rate = {"玉米": 80, "小麦": 110, "水稻": 150, "花生": 50, "蔬菜": 30, "果树": 40}

    rows = []
    for r in records:
        try:
            features = build_features(r)
            rows.append(features)
        except Exception as e:
            rows.append(None)

    valid_idx = [i for i, r in enumerate(rows) if r is not None]
    if not valid_idx:
        return []

    df = pd.DataFrame([rows[i] for i in valid_idx])
    for c in bundle["cat_cols"]:
        df[c], _ = pd.factorize(df[c])
    df = df[bundle["features"]]

    probs = bundle["model"].predict(df)

    results = []
    for k, i in enumerate(valid_idx):
        prob = float(probs[k])
        tier = assign_tier(prob)
        # 资产负债率约束：LTV ≥ 70% → 至少升级为高风险
        ltv = compute_ltv(records[i])
        if ltv is not None and ltv >= LTV_HIGH_RISK_THRESHOLD and tier in ("低风险", "中风险"):
            tier = "高风险"
        # 硬性规则覆盖：连三累六 → 拒贷（最高优先级）
        rejected, reject_reasons = check_reject_rules(records[i])
        if rejected:
            tier = "拒贷"
        results.append({
            "index": i,
            "name": records[i].get("name", f"客户{i+1}"),
            "id_tail": records[i].get("id_tail", "***"),
            "crop": records[i].get("crop", ""),
            "true_area": records[i].get("true_area", 0),
            "has_greenhouse": records[i].get("has_greenhouse", "否"),
            "probability": prob,
            "tier": tier,
            "reject_reasons": reject_reasons,
            "ltv": ltv,
        })
    return results


def load_metrics():
    """加载模型性能指标"""
    metrics_path = _HERE.parent.parent / "output" / "farm_metrics.json"
    if metrics_path.exists():
        with open(metrics_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def load_real_metrics():
    """加载真实数据指标"""
    metrics_path = _HERE.parent.parent / "output" / "real_metrics.json"
    if metrics_path.exists():
        with open(metrics_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None
