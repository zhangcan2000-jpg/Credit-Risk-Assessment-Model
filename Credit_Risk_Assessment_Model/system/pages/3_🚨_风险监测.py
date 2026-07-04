"""
风险监测页面
==================================
评估历史、高风险预警、客户追踪
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
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(
    page_title="风险监测 - 农户信贷智能风险分层系统",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded",
)

from core.config import HISTORY_DIR


# ===== 客户信息脱敏 =====
def mask_name(name):
    """姓名脱敏：保留首字，其余用 * 替换"""
    if not name or not isinstance(name, str) or name == "(未填写)":
        return name or "-"
    if len(name) == 1:
        return "*"
    return name[0] + "*" * (len(name) - 1)


def mask_id(id_card):
    """身份证号脱敏：保留前 3 位和后 3 位"""
    if not id_card:
        return "***"
    s = str(id_card).strip()
    if len(s) <= 6:
        return "*" * len(s)
    return s[:3] + "*" * (len(s) - 6) + s[-3:]


# 眼睛 SVG 图标（睁眼 / 闭眼）
EYE_OPEN_SVG = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>'
EYE_CLOSED_SVG = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>'


def pii_pair(plain_value, masker):
    """生成同时含明文与脱敏值的 span 对（默认脱敏显示，明文 display:none）"""
    plain = str(plain_value) if plain_value is not None else "-"
    masked = masker(plain_value)
    return (
        f'<span class="pii-masked">{masked}</span>'
        f'<span class="pii-plain" style="display:none">{plain}</span>'
    )


def inject_eye_script():
    """注入全局 JS：监听 .eye-btn 点击事件，切换该卡片内的明文/脱敏显示"""
    st.components.v1.html(f"""
    <script>
    (function() {{
        const OPEN = `{EYE_OPEN_SVG}`;
        const CLOSED = `{EYE_CLOSED_SVG}`;
        function bindEyes() {{
            const doc = window.parent.document;
            const btns = doc.querySelectorAll('.pii-card .eye-btn:not([data-bound])');
            btns.forEach(btn => {{
                btn.dataset.bound = '1';
                btn.innerHTML = OPEN;
                btn.addEventListener('click', () => {{
                    const card = btn.closest('.pii-card');
                    const maskedEls = card.querySelectorAll('.pii-masked');
                    const plainEls = card.querySelectorAll('.pii-plain');
                    const isMasked = maskedEls.length && maskedEls[0].style.display !== 'none';
                    maskedEls.forEach(el => el.style.display = isMasked ? 'none' : '');
                    plainEls.forEach(el => el.style.display = isMasked ? '' : 'none');
                    btn.innerHTML = isMasked ? CLOSED : OPEN;
                }});
            }});
        }}
        const doc = window.parent.document;
        const obs = new MutationObserver(bindEyes);
        obs.observe(doc.body, {{childList: true, subtree: true}});
        bindEyes();
    }})();
    </script>
    """, height=0)


def _fmt(v):
    """格式化字段值用于表格展示"""
    if v is None:
        return "-"
    if isinstance(v, float):
        if abs(v) >= 100:
            return f"{v:,.0f}"
        return f"{v:.4f}".rstrip("0").rstrip(".")
    return str(v)


def render_record_detail(r):
    """渲染单条历史记录的详情面板"""
    cust = r.get("customer", {})
    result = r.get("result", {})
    actions = result.get("actions") or {}

    # ===== 评估结果 =====
    tier = result.get("tier", "-")
    prob = result.get("probability")
    ltv = result.get("ltv")
    reject_reasons = result.get("reject_reasons") or []

    tier_color = {"低风险": "#28a745", "中风险": "#ffc107", "高风险": "#dc3545", "拒贷": "#7a1f1f"}.get(tier, "#6c757d")

    st.markdown(f"""
    <div style="background:{tier_color}10; border-left:4px solid {tier_color};
                padding:0.8rem 1rem; border-radius:6px; margin-bottom:0.8rem;">
        <strong style="color:{tier_color};">{tier}</strong>
        <span style="margin-left:1rem; color:#6c757d;">违约概率 <strong>{prob:.2%}</strong></span>
        {f'<span style="margin-left:1rem; color:#6c757d;">LTV <strong>{ltv:.0%}</strong></span>' if ltv is not None else ''}
    </div>
    """, unsafe_allow_html=True)

    if reject_reasons:
        st.error("⛔ 触发硬性拒贷规则：" + "；".join(reject_reasons))

    # ===== 客户基本信息 =====
    st.markdown("**👤 客户基本信息**")
    basic_rows = [
        ("姓名", _fmt(cust.get("name"))),
        ("身份证号", _fmt(cust.get("id_card") or cust.get("id_tail"))),
        ("年龄", _fmt(cust.get("age"))),
        ("性别", _fmt(cust.get("gender"))),
        ("婚姻状况", _fmt(cust.get("marital"))),
        ("受教育程度", _fmt(cust.get("education"))),
        ("种植作物", _fmt(cust.get("crop"))),
    ]
    st.dataframe(pd.DataFrame(basic_rows, columns=["字段", "值"]), use_container_width=True, hide_index=True)

    # ===== 经营信息 =====
    if any(cust.get(k) is not None for k in ["true_area", "reported_area", "subsidy_area",
                                              "has_greenhouse", "is_drought_year", "weather_score", "price_change"]):
        st.markdown("**🌾 经营信息**")
        biz_rows = [
            ("真实种植面积(亩)", _fmt(cust.get("true_area"))),
            ("自报种植面积(亩)", _fmt(cust.get("reported_area"))),
            ("补贴种植面积(亩)", _fmt(cust.get("subsidy_area"))),
            ("是否种植大棚", cust.get("has_greenhouse")),
            ("当年是否灾害", cust.get("is_drought_year")),
            ("气象年景评分", _fmt(cust.get("weather_score"))),
            ("农产品价格同比", _fmt(cust.get("price_change"))),
        ]
        st.dataframe(pd.DataFrame(biz_rows, columns=["字段", "值"]), use_container_width=True, hide_index=True)

    # ===== 财务信息 =====
    if any(cust.get(k) is not None for k in ["true_income", "reported_income", "loan_amount",
                                              "loan_term", "has_other_loan", "overdue_count_history",
                                              "consecutive_overdue", "total_assets", "total_liabilities"]):
        st.markdown("**💰 财务与信贷信息**")
        fin_rows = [
            ("测算真实年收入(元)", _fmt(cust.get("true_income"))),
            ("自报年收入(元)", _fmt(cust.get("reported_income"))),
            ("申请贷款金额(元)", _fmt(cust.get("loan_amount"))),
            ("贷款期限(月)", _fmt(cust.get("loan_term"))),
            ("是否有其他贷款", cust.get("has_other_loan")),
            ("近两年累计逾期次数", _fmt(cust.get("overdue_count_history"))),
            ("近两年最长连续逾期次数", _fmt(cust.get("consecutive_overdue"))),
            ("家庭总资产(元)", _fmt(cust.get("total_assets"))),
            ("家庭总负债(元)", _fmt(cust.get("total_liabilities"))),
        ]
        st.dataframe(pd.DataFrame(fin_rows, columns=["字段", "值"]), use_container_width=True, hide_index=True)

    # ===== 风险因子 =====
    risk_factors = result.get("risk_factors") or []
    if risk_factors:
        st.markdown("**🔍 关键风险因子**")
        sev_color = {"严重": "#dc3545", "中等": "#ffc107", "轻微": "#17a2b8"}
        for f in risk_factors:
            sev = f.get("severity", "中等")
            color = sev_color.get(sev, "#6c757d")
            st.markdown(f"""
            <div style="background:white; padding:0.5rem 0.8rem; border-radius:6px;
                        border-left:3px solid {color}; margin:0.3rem 0; font-size:0.85rem;">
                <strong>{f.get('factor', '')}</strong>
                <span style="margin-left:0.5rem; color:{color};">[{sev}]</span>
                <span style="margin-left:0.5rem; color:#495057;">{f.get('value', '')}</span>
                <div style="color:#6c757d; font-size:0.8rem; margin-top:0.2rem;">{f.get('explanation', '')}</div>
            </div>
            """, unsafe_allow_html=True)

    # ===== 差异化措施 =====
    if actions:
        st.markdown("**📋 差异化授信建议**")
        action_rows = [
            ("🏦 贷款方式", actions.get("loan_strategy", "-")),
            ("💲 利率策略", actions.get("rate_strategy", "-")),
            ("💵 额度策略", actions.get("amount_strategy", "-")),
            ("⚙️ 审批流程", actions.get("process_strategy", "-")),
            ("👁️ 贷后监测", actions.get("monitor_strategy", "-")),
        ]
        st.dataframe(pd.DataFrame(action_rows, columns=["项目", "措施"]), use_container_width=True, hide_index=True)


def load_history():
    """加载单户评估历史"""
    history_file = HISTORY_DIR / "evaluations.json"
    if not history_file.exists():
        return []
    with open(history_file, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return []


def load_batch_history():
    history_file = HISTORY_DIR / "batch_history.json"
    if not history_file.exists():
        return []
    with open(history_file, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return []


def main():
    st.markdown("# 🚨 风险监测中心")
    st.caption("评估历史、风险分布统计、高风险预警")

    st.markdown("---")

    history = load_history()
    batch_history = load_batch_history()

    if not history and not batch_history:
        st.info("""
        📭 暂无评估记录

        请先到 **👤 单户评估** 或 **📋 批量评估** 页面进行评估。

        评估完成后，本页面将展示：
        - 历史评估记录
        - 风险分布统计
        - 高风险客户预警
        """)
        return

    # ===== 概览 =====
    st.markdown("### 📊 评估总览")
    total_individual = len(history)
    total_batch_records = sum(b.get("total", 0) for b in batch_history)
    total_evaluations = total_individual + total_batch_records

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("总评估次数", f"{len(history) + len(batch_history)}")
    with c2:
        st.metric("评估客户数", f"{total_evaluations}")
    with c3:
        st.metric("单户评估", f"{total_individual}")
    with c4:
        st.metric("批量评估", f"{total_batch_records}")

    st.markdown("---")

    # ===== 风险分布 =====
    if history:
        st.markdown("### 🎯 风险等级分布（单户评估）")
        tier_data = [r["result"]["tier"] for r in history]
        df_tier = pd.DataFrame(tier_data, columns=["tier"])
        tier_count = df_tier["tier"].value_counts().reindex(["低风险", "中风险", "高风险"]).fillna(0)

        col_dist1, col_dist2 = st.columns([1, 2])
        with col_dist1:
            colors = {"低风险": "#28a745", "中风险": "#ffc107", "高风险": "#dc3545"}
            for tier in ["低风险", "中风险", "高风险"]:
                count = int(tier_count.get(tier, 0))
                pct = count / max(len(tier_data), 1) * 100
                st.markdown(f"""
                <div style="background:{colors[tier]}20; border-left:4px solid {colors[tier]};
                            padding:1rem; margin:0.5rem 0; border-radius:6px;">
                    <strong style="color:{colors[tier]};">{tier}</strong>
                    <span style="float:right; font-weight:bold; color:{colors[tier]};">
                        {count} 户 ({pct:.1f}%)
                    </span>
                </div>
                """, unsafe_allow_html=True)

        with col_dist2:
            fig = px.pie(
                values=tier_count.values,
                names=tier_count.index,
                color=tier_count.index,
                color_discrete_map=colors,
                hole=0.4,
            )
            fig.update_layout(height=300, showlegend=True, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")

    # ===== 高风险预警 =====
    if history:
        st.markdown("### 🚨 高风险客户预警")
        high_risk = [r for r in history if r["result"]["tier"] in ("高风险", "拒贷")]
        if high_risk:
            st.error(f"⚠️ 共识别到 **{len(high_risk)}** 户高风险/拒贷客户，需重点监测")
            high_risk_sorted = sorted(high_risk, key=lambda x: x["result"]["probability"], reverse=True)
            for i, r in enumerate(high_risk_sorted[:20], 1):
                cust = r["customer"]
                prob = r["result"]["probability"]
                raw_id = cust.get("id_card") or cust.get("id_tail", "***")
                name_html = pii_pair(cust.get("name", "未知"), mask_name)
                id_html = pii_pair(raw_id, mask_id)
                st.markdown(f"""
                <div class="pii-card" style="position:relative; background:#f8d7da; border-left:5px solid #dc3545; padding:1rem; margin:0.5rem 0; border-radius:6px;">
                    <button class="eye-btn" title="点击切换明文/脱敏"
                        style="position:absolute; top:8px; right:10px; background:transparent; border:none; cursor:pointer; color:#6c757d; padding:4px; line-height:0;"></button>
                    <div style="display:flex; justify-content:space-between; padding-right:36px;">
                        <div>
                            <strong>#{i} {name_html}</strong>
                            <span style="margin-left:1rem; color:#6c757d;">身份证号：{id_html}</span>
                        </div>
                        <strong style="color:#dc3545;">违约概率：{prob:.2%}</strong>
                    </div>
                    <div style="margin-top:0.4rem; color:#6c757d; font-size:0.9rem;">
                        种植作物：{cust.get('crop', '-')} · 面积：{cust.get('true_area', '-')}亩 · 评估时间：{r['timestamp']}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.success("✅ 当前无高风险客户")

        st.markdown("---")

    # ===== 历史记录 =====
    if history:
        st.markdown("### 📜 历史评估记录")
        history_sorted = sorted(history, key=lambda x: x["timestamp"], reverse=True)
        tier_color = {"低风险": "#28a745", "中风险": "#ffc107", "高风险": "#dc3545", "拒贷": "#7a1f1f"}

        if "detail_open" not in st.session_state:
            st.session_state.detail_open = {}

        for i, r in enumerate(history_sorted[:50], 1):
            cust = r["customer"]
            raw_id = cust.get("id_card") or cust.get("id_tail", "***")
            name_html = pii_pair(cust.get("name", "-"), mask_name)
            id_html = pii_pair(raw_id, mask_id)
            color = tier_color.get(r["result"]["tier"], "#6c757d")
            record_key = f"hist_{r.get('timestamp', '')}_{i}"

            st.markdown(f"""
            <div class="pii-card" style="position:relative; background:white; padding:0.6rem 1rem; margin:0.3rem 0;
                        border-radius:6px; border-left:4px solid {color}; font-size:0.9rem;">
                <button class="eye-btn" title="点击切换明文/脱敏"
                    style="position:absolute; top:6px; right:8px; background:transparent; border:none; cursor:pointer; color:#6c757d; padding:4px; line-height:0;"></button>
                <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:0.5rem; padding-right:36px;">
                    <div>
                        <strong>{name_html}</strong>
                        <span style="margin-left:0.5rem; color:#6c757d;">{id_html}</span>
                    </div>
                    <div style="color:#6c757d;">
                        {r['timestamp']} · {cust.get('crop', '-')} · {cust.get('true_area', '-')}亩
                    </div>
                    <div>
                        <span style="color:#6c757d;">违约概率</span>
                        <strong style="margin-left:0.3rem;">{r['result']['probability']:.2%}</strong>
                        <span style="margin-left:0.8rem; padding:0.1rem 0.5rem; border-radius:4px;
                                     background:{color}20; color:{color}; font-weight:bold;">
                            {r['result']['tier']}
                        </span>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # 详情按钮 + 展开面板
            is_open = st.session_state.detail_open.get(record_key, False)
            btn_col, _ = st.columns([1, 8])
            with btn_col:
                if st.button(
                    "🔼 收起详情" if is_open else "📋 查看详情",
                    key=f"btn_{record_key}",
                    use_container_width=False,
                ):
                    st.session_state.detail_open[record_key] = not is_open
                    st.rerun()
            if is_open:
                render_record_detail(r)
                st.markdown("---")

    # 注入眼睛按钮的交互脚本
    inject_eye_script()

    # ===== 批量评估历史 =====
    if batch_history:
        st.markdown("---")
        st.markdown("### 📋 批量评估历史")
        batch_sorted = sorted(batch_history, key=lambda x: x["timestamp"], reverse=True)
        batch_data = []
        for b in batch_sorted[:20]:
            s = b.get("summary", {})
            batch_data.append({
                "时间": b["timestamp"],
                "评估数量": b.get("total", 0),
                "低风险": s.get("低风险", 0),
                "中风险": s.get("中风险", 0),
                "高风险": s.get("高风险", 0),
            })
        st.dataframe(pd.DataFrame(batch_data), use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
