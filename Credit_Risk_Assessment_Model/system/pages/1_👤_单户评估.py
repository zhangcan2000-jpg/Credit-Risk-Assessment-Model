"""
单户风险评估页面
==================================
输入农户信息 → 实时输出风险等级、差异化措施、风险因子解释
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
import re
from datetime import datetime, date
import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="单户评估 - 农户信贷智能风险分层系统",
    page_icon="👤",
    layout="wide",
    initial_sidebar_state="expanded",
)

from core.predictor import predict, get_model
from system.core.config import (
    SYSTEM_NAME, ORGANIZATION, RESPONSIBLE,
    HISTORY_DIR, CROP_SUBSIDY_RATE, CROP_REVENUE_RATE
)


# ===== 输入校验与解析工具 =====
def _sanitize_name():
    """白名单：只保留中文（含生僻字、汉字〇）、少数民族间隔号·、空格"""
    name = st.session_state.customer_name
    # 一-鿿 CJK基本  㐀-䶿 CJK扩展A  〇 汉字"〇"  ··・ 间隔号
    cleaned = re.sub(r'[^一-鿿㐀-䶿〇·・ ]', '', name)
    if cleaned != name:
        st.session_state.customer_name = cleaned
        st.session_state.name_cleaned = True
    else:
        st.session_state.name_cleaned = False


def _sanitize_id():
    """身份证号只保留数字和 X/x，并截断为 18 位"""
    idc = st.session_state.customer_id
    cleaned = re.sub(r'[^0-9Xx]', '', idc)[:18]
    if cleaned != idc:
        st.session_state.customer_id = cleaned
        st.session_state.id_cleaned = True
    else:
        st.session_state.id_cleaned = False


def parse_id_card(id_card):
    """
    解析 18 位身份证号，返回出生日期/年龄/性别。
    返回 None 表示无法解析。
    """
    if not id_card or len(id_card) != 18:
        return None
    if not re.match(r'^\d{17}[\dXx]$', id_card):
        return None
    birth_str = id_card[6:14]
    try:
        birth = datetime.strptime(birth_str, "%Y%m%d").date()
    except ValueError:
        return None
    today = date.today()
    age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
    # 第 17 位（索引16）奇=男 偶=女
    gender = "男" if int(id_card[16]) % 2 == 1 else "女"
    return {"birth": birth, "age": age, "gender": gender}


# 身份证校验位算法（GB 11643-1999）
_ID_CHECK_FACTORS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
_ID_CHECK_CODES = ['1', '0', 'X', '9', '8', '7', '6', '5', '4', '3', '2']


def verify_id_card_check_digit(id_card):
    """验证身份证号第 18 位校验码是否正确。True 表示校验位正确。"""
    if not id_card or len(id_card) != 18:
        return False
    if not re.match(r'^\d{17}[\dXx]$', id_card):
        return False
    total = sum(int(id_card[i]) * _ID_CHECK_FACTORS[i] for i in range(17))
    expected = _ID_CHECK_CODES[total % 11]
    return id_card[17].upper() == expected


def save_history(result, customer_info):
    """保存评估历史"""
    history_file = HISTORY_DIR / "evaluations.json"
    history = []
    if history_file.exists():
        with open(history_file, "r", encoding="utf-8") as f:
            try:
                history = json.load(f)
            except Exception:
                history = []

    # 完整保存客户输入与评估结果，供风险监测页面"查看详情"使用
    full_customer = dict(customer_info)
    if "input_data" in result and isinstance(result["input_data"], dict):
        full_customer.update(result["input_data"])

    record = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "customer": full_customer,
        "result": {
            "probability": result["probability"],
            "tier": result["tier"],
            "risk_factors": result.get("risk_factors", []),
            "reject_reasons": result.get("reject_reasons", []),
            "ltv": result.get("ltv"),
            "actions": result.get("actions"),
        },
    }
    history.append(record)
    history = history[-200:]  # 保留最近200条

    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def main():
    st.markdown(f"# 👤 单户风险评估")
    st.caption("输入农户信息，系统将实时输出风险等级与差异化授信建议")
    st.markdown("---")

    # ===== 输入区 =====
    st.markdown("### 📝 一、客户基本信息")

    st.markdown("#### 🪪 身份信息")

    # 初始化 session_state
    if "customer_name" not in st.session_state:
        st.session_state.customer_name = ""
    if "customer_id" not in st.session_state:
        st.session_state.customer_id = ""

    # 客户姓名：不允许数字和字母
    customer_name = st.text_input(
        "客户姓名",
        key="customer_name",
        placeholder="请输入客户姓名（仅中文）",
        help="只能包含中文（含间隔号·），不允许数字、字母、标点或其他符号",
        on_change=_sanitize_name,
    )
    if st.session_state.get("name_cleaned"):
        st.toast("已自动过滤姓名中的非法字符（数字/字母/符号）", icon="⚠️")

    # 身份证号：不脱敏、只允许数字和 X、限制 18 位
    customer_id = st.text_input(
        "身份证号",
        key="customer_id",
        max_chars=18,
        placeholder="请输入 18 位身份证号",
        help="18 位身份证号（前 17 位数字 + 1 位数字或 X），输入完整后自动识别年龄与性别",
        on_change=_sanitize_id,
    )
    if st.session_state.get("id_cleaned"):
        st.toast("已自动过滤身份证号中的非法字符", icon="⚠️")

    # 从身份证号自动识别年龄与性别
    id_info = parse_id_card(st.session_state.customer_id)
    auto_age = id_info["age"] if id_info else None
    auto_gender = id_info["gender"] if id_info else None

    # 身份证格式 + 校验位提示
    if st.session_state.customer_id and len(st.session_state.customer_id) == 18:
        if id_info is None:
            st.warning("⚠️ 身份证号格式有误，请检查出生日期段")
        elif not verify_id_card_check_digit(st.session_state.customer_id):
            st.warning("⚠️ 身份证校验位不正确，请核对第 18 位（应为大写 X 或数字）")
        else:
            st.caption(f"✅ 已识别：出生日期 {id_info['birth']:%Y-%m-%d}，年龄 {auto_age} 岁，性别 {auto_gender}")

    st.markdown("#### 📇 基础画像")

    col1, col2, col3 = st.columns(3)
    with col1:
        # 年龄：身份证识别后填充并禁用，否则显示 placeholder
        if auto_age is not None:
            age = st.number_input(
                "年龄（身份证识别）", 18, 100, value=auto_age, step=1,
                disabled=True,
                help=f"根据身份证号自动识别为 {auto_age} 岁",
            )
        else:
            age = st.number_input(
                "年龄", 18, 100, value=None, step=1,
                placeholder="请输入",
                help="请先填写身份证号自动识别，或手动输入",
            )
        # 性别：身份证识别后填充并禁用，否则显示 placeholder
        if auto_gender is not None:
            gender = st.selectbox(
                "性别（身份证识别）", ["男", "女"],
                index=["男", "女"].index(auto_gender),
                disabled=True,
                help="根据身份证第 17 位自动识别",
            )
        else:
            gender = st.selectbox(
                "性别", ["男", "女"],
                index=None, placeholder="请选择",
            )
        education = st.selectbox(
            "学历", ["小学及以下", "初中", "高中/中专", "大专及以上"],
            index=None, placeholder="请选择",
        )
    with col2:
        marital = st.selectbox(
            "婚姻状况", ["已婚", "未婚", "离异/丧偶"],
            index=None, placeholder="请选择",
        )
        crop = st.selectbox(
            "种植作物", list(CROP_SUBSIDY_RATE.keys()),
            index=None, placeholder="请选择",
        )
        subsidy_stable = st.selectbox(
            "补贴稳定领取", ["是", "否"],
            index=None, placeholder="请选择",
        )
    with col3:
        reported_area = st.number_input(
            "自报种植面积（亩）", min_value=1, value=None, step=1,
            placeholder="请输入",
            help="农户在贷款申请时自报的种植面积",
        )
        true_area = st.number_input(
            "真实种植面积（亩）", 1, 1000, value=None, step=1,
            placeholder="请输入",
        )
        subsidy_area = st.number_input(
            "补贴种植面积（亩）", 1, 1000, value=None, step=1,
            placeholder="请输入",
            help="农业补贴登记的实际发放面积",
        )

    st.markdown("---")
    st.markdown("### 🌤️ 二、生产经营信息")

    col4, col5, col6 = st.columns(3)

    # 先 col6：定义气象/价格，供 col5 计算建议真实收入
    with col6:
        # 气象年景：5 档选项映射 0~1 评分
        weather_options = [
            ("大幅增产 (0.90-1.00)", 1.00),
            ("小幅增产 (0.80-0.90)", 0.90),
            ("持平平稳 (0.70-0.80)", 0.80),
            ("小幅减产 (0.50-0.70)", 0.60),
            ("严重减产 (0.00-0.50)", 0.40),
        ]
        weather_label = st.selectbox(
            "气象年景",
            [k for k, _ in weather_options],
            index=None, placeholder="请选择",
            help="反映当年气象条件对作物产量的综合影响",
        )
        weather_score = dict(weather_options).get(weather_label) if weather_label else None

        # 农产品价格同比：5 档选项映射 +20%~-20%
        price_options = [
            ("明显上涨 (+15%~+30%)", 0.20),
            ("小幅上涨 (+5%~+15%)", 0.08),
            ("价格平稳 (-5%~+5%)", 0.00),
            ("小幅下跌 (-15%~-5%)", -0.08),
            ("明显下跌 (-30%~-15%)", -0.20),
        ]
        price_label = st.selectbox(
            "农产品价格同比",
            [k for k, _ in price_options],
            index=None, placeholder="请选择",
            help="今年农产品销售价格相对去年的涨跌幅度",
        )
        price_change = dict(price_options).get(price_label) if price_label else None

    # 再 col5：依赖 true_area/crop（col3/col2）+ weather_score/price_change（col6）
    with col5:
        # 计算建议真实收入，所有依赖项必须齐全
        can_calc = all(x is not None for x in [true_area, crop, weather_score, price_change])
        if can_calc:
            base_revenue = true_area * CROP_REVENUE_RATE.get(crop, 800)
            suggested_true_income = int(base_revenue * weather_score * (1 + price_change))
            # 限制在合法范围内，避免极端气象/价格下越界触发 Streamlit 报错
            suggested_true_income = max(2000, min(500000, suggested_true_income))
        else:
            suggested_true_income = None
        true_income = st.number_input(
            "测算真实年收入（元）", 2000, 500000, value=suggested_true_income, step=5000,
            placeholder="请输入",
            help=f"系统基于「面积×作物单价×气象×价格」自动测算，可手动调整"
        )
        loan_amount = st.number_input(
            "申请贷款金额（元）", 5000, 500000, value=None, step=5000,
            placeholder="请输入",
        )
        loan_term = st.selectbox(
            "贷款期限（月）", [6, 12, 24, 36],
            index=None, placeholder="请选择",
        )

    # 最后 col4：reported_income 默认值依赖 suggested_true_income（col5）
    with col4:
        has_greenhouse = st.selectbox(
            "是否种植大棚", ["否", "是"],
            index=None, placeholder="请选择",
            help="大棚种植抗灾能力强、收益更高，但前期投入大",
        )
        is_drought = st.selectbox(
            "当年是否灾害", ["否", "是"],
            index=None, placeholder="请选择",
        )
        reported_income = st.number_input(
            "自报年收入（元）", 2000, 1000000, value=suggested_true_income, step=5000,
            placeholder="请输入",
            help="农户在申请时自报的收入金额"
        )

    st.markdown("---")
    st.markdown("### 💰 三、信贷历史信息")

    col7, col8 = st.columns(2)
    with col7:
        has_other_loan = st.selectbox(
            "是否有其他贷款", ["否", "是"],
            index=None, placeholder="请选择",
        )
    with col8:
        overdue_count = st.number_input(
            "近两年累计逾期次数", min_value=0, value=None, step=1,
            placeholder="请输入",
            help="近 24 个月内累计逾期次数（≥6 次触发拒贷）",
        )

    col9a, col9b = st.columns(2)
    with col9a:
        consecutive_overdue = st.number_input(
            "近两年最长连续逾期次数", min_value=0, value=None, step=1,
            placeholder="请输入",
            help="近 24 个月内最长一次连续逾期月数（≥3 次触发拒贷，即'连三'）",
        )
    with col9b:
        st.empty()

    st.markdown("---")
    st.markdown("### 🏠 四、家庭资产负债")

    colA1, colA2 = st.columns(2)
    with colA1:
        total_assets = st.number_input(
            "家庭总资产（元）", min_value=0, value=None, step=10000,
            placeholder="请输入",
            help="房产、土地、农机、存款、其他投资等可变现资产合计",
        )
    with colA2:
        total_liabilities = st.number_input(
            "家庭总负债（元）", min_value=0, value=None, step=5000,
            placeholder="请输入",
            help="其他贷款、民间借款、信用卡欠款、应付账款等合计",
        )

    if total_assets and total_assets > 0 and total_liabilities is not None and loan_amount is not None:
        ltv_preview = (total_liabilities + loan_amount) / total_assets
        if ltv_preview >= 0.70:
            st.warning(f"⚠️ 当前 LTV = {ltv_preview:.0%} ≥ 70%，触发升级为高风险")
        elif ltv_preview >= 0.50:
            st.info(f"ℹ️ 当前 LTV = {ltv_preview:.0%}（50%~70% 区间，偿债压力上升）")

    st.markdown("---")

    # ===== 评估按钮 =====
    btn_col1, btn_col2 = st.columns([4, 1])
    with btn_col1:
        submit_clicked = st.button("🔮 开始风险评估", type="primary", use_container_width=True)
    with btn_col2:
        reset_clicked = st.button("🔄 清空重填", use_container_width=True)

    # 清空所有输入字段
    if reset_clicked:
        st.session_state.pop("customer_name", None)
        st.session_state.pop("customer_id", None)
        st.rerun()

    if submit_clicked:
        # 必填字段校验（None 表示未填写）
        missing = []
        if not customer_name: missing.append("客户姓名")
        if not customer_id or len(customer_id) != 18: missing.append("身份证号（18位）")
        if age is None: missing.append("年龄")
        if gender is None: missing.append("性别")
        if education is None: missing.append("学历")
        if marital is None: missing.append("婚姻状况")
        if crop is None: missing.append("种植作物")
        if subsidy_stable is None: missing.append("补贴稳定领取")
        if reported_area is None: missing.append("自报种植面积")
        if true_area is None: missing.append("真实种植面积")
        if subsidy_area is None: missing.append("补贴种植面积")
        if has_greenhouse is None: missing.append("是否种植大棚")
        if is_drought is None: missing.append("当年是否灾害")
        if weather_score is None: missing.append("气象年景")
        if price_change is None: missing.append("农产品价格同比")
        if true_income is None: missing.append("测算真实年收入")
        if reported_income is None: missing.append("自报年收入")
        if loan_amount is None: missing.append("申请贷款金额")
        if loan_term is None: missing.append("贷款期限")
        if has_other_loan is None: missing.append("是否有其他贷款")
        if overdue_count is None: missing.append("近两年累计逾期次数")
        if consecutive_overdue is None: missing.append("近两年最长连续逾期次数")
        if total_assets is None: missing.append("家庭总资产")
        if total_liabilities is None: missing.append("家庭总负债")

        if missing:
            st.warning(f"⚠️ 请完善以下字段：{', '.join(missing)}")
            st.stop()

        with st.spinner("正在调用模型评估..."):
            try:
                input_data = {
                    "age": age,
                    "gender": gender,
                    "marital": marital,
                    "education": education,
                    "crop": crop,
                    "true_area": true_area,
                    "reported_area": reported_area,
                    "subsidy_area": subsidy_area,
                    "subsidy_stable": subsidy_stable,
                    "is_drought_year": is_drought,
                    "has_greenhouse": has_greenhouse,
                    "weather_score": weather_score,
                    "price_change": price_change,
                    "true_income": true_income,
                    "reported_income": reported_income,
                    "loan_amount": loan_amount,
                    "loan_term": loan_term,
                    "has_other_loan": has_other_loan,
                    "overdue_count_history": overdue_count,
                    "consecutive_overdue": consecutive_overdue,
                    "total_assets": total_assets,
                    "total_liabilities": total_liabilities,
                }

                result = predict(input_data)
                result["input_data"] = input_data
                save_history(result, {
                    "name": customer_name or "(未填写)",
                    "id_card": customer_id or "",
                    "crop": crop,
                    "true_area": true_area,
                })

                st.markdown("---")
                st.markdown("## 🎯 评估结果")
                st.balloons()

                # ===== 概要 =====
                prob = result["probability"]
                tier = result["tier"]
                actions = result["actions"]

                if tier == "低风险":
                    bg_class = "risk-low"
                    color = "#155724"
                elif tier == "中风险":
                    bg_class = "risk-mid"
                    color = "#856404"
                elif tier == "拒贷":
                    bg_class = "risk-reject"
                    color = "#ffffff"
                else:
                    bg_class = "risk-high"
                    color = "#721c24"

                bg_style = "background:#7a1f1f;" if tier == "拒贷" else ""
                st.markdown(f"""
                <div class="risk-card-{bg_class}" style="padding:1.5rem; margin:1rem 0; {bg_style}">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div>
                            <h2 style="margin:0; color:{color};">{actions['icon']} 风险等级：{tier}</h2>
                            <p style="margin:0.3rem 0 0 0; color:{color}; font-size:1.1rem;">{actions['summary']}</p>
                        </div>
                        <div style="text-align:right;">
                            <p style="margin:0; color:{color}; font-size:0.9rem;">违约概率</p>
                            <h2 style="margin:0; color:{color};">{prob:.2%}</h2>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # ===== 核心指标 =====
                c1, c2, c3 = st.columns(3)
                with c1:
                    if reported_area > 0:
                        area_diff = (reported_area - subsidy_area) / max(subsidy_area, 1)
                        st.metric("⚖️ 面积差异率", f"{area_diff:+.1%}",
                                  delta="申报存疑" if area_diff > 0.1 else "正常",
                                  delta_color="inverse")
                    else:
                        st.metric("⚖️ 面积差异率", "0%")
                with c2:
                    debt_ratio = loan_amount / max(true_income, 1)
                    st.metric("💰 贷款/收入比", f"{debt_ratio:.2f}")
                with c3:
                    ltv = result.get("ltv")
                    if ltv is not None:
                        st.metric(
                            "🏠 资产负债率 (LTV)",
                            f"{ltv:.0%}",
                            delta="超标" if ltv >= 0.7 else ("偏高" if ltv >= 0.5 else "健康"),
                            delta_color="inverse",
                        )
                    else:
                        st.metric("🏠 资产负债率 (LTV)", "-")

                st.markdown("---")

                # ===== 差异化措施 =====
                st.markdown("### 📋 差异化授信建议")
                st.markdown(f"""
                <div style="background:white; padding:1.5rem; border-radius:10px; box-shadow:0 2px 6px rgba(0,0,0,0.08);">
                    <table style="width:100%; border-collapse:collapse;">
                        <tr>
                            <td style="padding:0.6rem; width:25%; background:#f8f9fa; font-weight:bold;">🏦 贷款方式</td>
                            <td style="padding:0.6rem;">{actions['loan_strategy']}</td>
                        </tr>
                        <tr>
                            <td style="padding:0.6rem; background:#f8f9fa; font-weight:bold;">💲 利率策略</td>
                            <td style="padding:0.6rem;">{actions['rate_strategy']}</td>
                        </tr>
                        <tr>
                            <td style="padding:0.6rem; background:#f8f9fa; font-weight:bold;">💵 额度策略</td>
                            <td style="padding:0.6rem;">{actions['amount_strategy']}</td>
                        </tr>
                        <tr>
                            <td style="padding:0.6rem; background:#f8f9fa; font-weight:bold;">⚙️ 审批流程</td>
                            <td style="padding:0.6rem;">{actions['process_strategy']}</td>
                        </tr>
                        <tr>
                            <td style="padding:0.6rem; background:#f8f9fa; font-weight:bold;">👁️ 贷后监测</td>
                            <td style="padding:0.6rem;">{actions['monitor_strategy']}</td>
                        </tr>
                    </table>
                </div>
                """, unsafe_allow_html=True)

                st.markdown("---")

                # ===== 风险因子 =====
                st.markdown("### 🔍 关键风险因子解释")
                risk_factors = result["risk_factors"]

                if not risk_factors:
                    st.success("✅ 未识别到明显风险因子，客户整体风险可控。")
                else:
                    st.markdown(f"""
                    <div style="background:#fff3cd; padding:1rem; border-radius:8px; border-left:4px solid #ffc107; margin-bottom:1rem;">
                        共识别到 <strong>{len(risk_factors)}</strong> 个风险因子，按严重程度排序如下：
                    </div>
                    """, unsafe_allow_html=True)

                    severity_color = {"严重": "#dc3545", "中等": "#ffc107", "轻微": "#17a2b8"}
                    severity_bg = {"严重": "#f8d7da", "中等": "#fff3cd", "轻微": "#d1ecf1"}

                    for i, f in enumerate(risk_factors, 1):
                        sev = f["severity"]
                        st.markdown(f"""
                        <div style="background:white; padding:1rem; border-radius:8px; margin-bottom:0.8rem; border-left:4px solid {severity_color[sev]};">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <div>
                                    <strong style="color:#343a40;">{i}. {f['factor']}</strong>
                                    <span style="margin-left:1rem; background:{severity_bg[sev]}; color:{severity_color[sev]}; padding:0.2rem 0.6rem; border-radius:10px; font-size:0.85rem;">{sev}</span>
                                </div>
                                <div style="font-weight:bold; color:{severity_color[sev]};">{f['value']}</div>
                            </div>
                            <p style="margin:0.5rem 0 0 0; color:#6c757d; font-size:0.9rem;">{f['explanation']}</p>
                        </div>
                        """, unsafe_allow_html=True)

                # ===== 底部说明 =====
                st.markdown("---")
                st.info("💡 本评估结果由 AI 模型生成，仅供信贷决策参考，最终决策需结合人工审核与现场调查。")

            except FileNotFoundError as e:
                st.error(f"⚠️ {str(e)}")
            except Exception as e:
                st.error(f"⚠️ 评估失败：{str(e)}")


if __name__ == "__main__":
    main()
