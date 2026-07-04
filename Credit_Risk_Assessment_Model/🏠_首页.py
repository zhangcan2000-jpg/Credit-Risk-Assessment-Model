"""
农户信贷智能风险分层系统 V1.0
================================
2026年"数据要素×"大赛山东分赛 - 现代农业赛道
青岛农商银行即墨支行

启动方式：
    cd system
    streamlit run app.py
"""
import os
import sys

# 安全重定向 stdout（仅命令行执行时需要，Streamlit 环境会跳过）
try:
    import io
    if hasattr(sys.stdout, 'buffer') and sys.stdout.buffer is not None:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
except (ValueError, AttributeError, io.UnsupportedOperation):
    pass

import streamlit as st
from system.core.config import (
    SYSTEM_FULL_NAME, SYSTEM_NAME, SYSTEM_VERSION,
    ORGANIZATION, DEVELOPER, RESPONSIBLE,
    COMPETITION, TRACK, PROJECT_NAME
)
from core.predictor import load_metrics, load_real_metrics

# ===== 页面配置 =====
st.set_page_config(
    page_title=f"{SYSTEM_NAME}",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ===== 自定义样式 =====
st.markdown("""
<style>
    /* 主背景 */
    .stApp {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
    }
    /* 标题区域 */
    .main-header {
        background: linear-gradient(135deg, #1b5e20 0%, #2e7d32 100%);
        padding: 2rem;
        border-radius: 12px;
        color: white;
        text-align: center;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }
    .main-header h1 {
        margin: 0;
        font-size: 2rem;
        font-weight: 700;
    }
    .main-header p {
        margin: 0.5rem 0 0 0;
        opacity: 0.9;
        font-size: 1rem;
    }
    /* 指标卡片 */
    .metric-card {
        background: white;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.08);
        text-align: center;
        border-top: 4px solid #1b5e20;
    }
    .metric-card .value {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1b5e20;
        margin: 0.3rem 0;
    }
    .metric-card .label {
        font-size: 0.95rem;
        color: #495057;
        margin: 0;
    }
    /* 风险卡片 */
    .risk-card-low {
        background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%);
        border-left: 5px solid #28a745;
        padding: 1.2rem; border-radius: 8px;
    }
    .risk-card-mid {
        background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%);
        border-left: 5px solid #ffc107;
        padding: 1.2rem; border-radius: 8px;
    }
    .risk-card-high {
        background: linear-gradient(135deg, #f8d7da 0%, #f5b7b1 100%);
        border-left: 5px solid #dc3545;
        padding: 1.2rem; border-radius: 8px;
    }
    /* 信息卡片 */
    .info-card {
        background: white;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.08);
        min-height: 200px;
        box-sizing: border-box;
    }
    .footer {
        text-align: center;
        color: #6c757d;
        font-size: 0.85rem;
        margin-top: 2rem;
        padding-top: 1rem;
        border-top: 1px solid #dee2e6;
    }
</style>
""", unsafe_allow_html=True)


def main():
    # ===== 顶部标题 =====
    st.markdown(f"""
    <div class="main-header">
        <h1>🌾 {SYSTEM_NAME} {SYSTEM_VERSION}</h1>
        <p>{PROJECT_NAME}</p>
        <p style="font-size:0.85rem; margin-top:0.5rem; opacity:0.85;">
            {ORGANIZATION} · {DEVELOPER} · 负责人：{RESPONSIBLE}
        </p>
    </div>
    """, unsafe_allow_html=True)

    metrics = load_real_metrics()
    farm_metrics = load_metrics()

    # ===== 风险分层效果 =====
    st.markdown("### 🎯 三档风险分层效果（真实数据验证）")
    st.markdown("---")

    if metrics and "tier_stats" in metrics:
        col_a, col_b, col_c = st.columns(3)
        tiers = {t["风险等级"]: t for t in metrics["tier_stats"]}

        with col_a:
            t = tiers.get("低风险", {})
            st.markdown(f"""
            <div class="risk-card-low">
                <h4 style="margin:0; color:#155724;">✅ 低风险</h4>
                <p style="margin:0.5rem 0; font-size:1.5rem; font-weight:700; color:#155724;">{t.get('样本占比%', 0)}%</p>
                <p style="margin:0; color:#155724;">样本占比</p>
                <hr style="margin:0.5rem 0; border-color:#a8d8b9;">
                <p style="margin:0; color:#155724;">实际违约率：<strong>{t.get('实际违约率%', 0)}%</strong></p>
            </div>
            """, unsafe_allow_html=True)

        with col_b:
            t = tiers.get("中风险", {})
            st.markdown(f"""
            <div class="risk-card-mid">
                <h4 style="margin:0; color:#856404;">⚠️ 中风险</h4>
                <p style="margin:0.5rem 0; font-size:1.5rem; font-weight:700; color:#856404;">{t.get('样本占比%', 0)}%</p>
                <p style="margin:0; color:#856404;">样本占比</p>
                <hr style="margin:0.5rem 0; border-color:#ffeaa7;">
                <p style="margin:0; color:#856404;">实际违约率：<strong>{t.get('实际违约率%', 0)}%</strong></p>
            </div>
            """, unsafe_allow_html=True)

        with col_c:
            t = tiers.get("高风险", {})
            st.markdown(f"""
            <div class="risk-card-high">
                <h4 style="margin:0; color:#721c24;">🚨 高风险</h4>
                <p style="margin:0.5rem 0; font-size:1.5rem; font-weight:700; color:#721c24;">{t.get('样本占比%', 0)}%</p>
                <p style="margin:0; color:#721c24;">样本占比</p>
                <hr style="margin:0.5rem 0; border-color:#f5b7b1;">
                <p style="margin:0; color:#721c24;">实际违约率：<strong>{t.get('实际违约率%', 0)}%</strong></p>
            </div>
            """, unsafe_allow_html=True)

    st.write("")

    # ===== 系统功能 =====
    st.markdown("### 🔧 系统功能模块")
    st.markdown("---")

    col_f1, col_f2, col_f3 = st.columns(3)

    with col_f1:
        st.markdown("""
        <div class="info-card" style="text-align:center;">
            <div style="font-size:2.5rem;">👤</div>
            <h4 style="color:#1b5e20;">单户评估</h4>
            <p style="font-size:0.9rem; color:#495057;">输入农户信息，实时输出风险等级与差异化措施</p>
        </div>
        """, unsafe_allow_html=True)

    with col_f2:
        st.markdown("""
        <div class="info-card" style="text-align:center;">
            <div style="font-size:2.5rem;">📋</div>
            <h4 style="color:#1b5e20;">批量评估</h4>
            <p style="font-size:0.9rem; color:#495057;">上传CSV批量评估，自动生成风险评估报告</p>
        </div>
        """, unsafe_allow_html=True)

    with col_f3:
        st.markdown("""
        <div class="info-card" style="text-align:center;">
            <div style="font-size:2.5rem;">🚨</div>
            <h4 style="color:#1b5e20;">风险监测</h4>
            <p style="font-size:0.9rem; color:#495057;">评估历史记录、高风险预警、客户追踪</p>
        </div>
        """, unsafe_allow_html=True)

    st.write("")

    # ===== 核心创新 =====
    st.markdown("### 💡 核心创新点")
    st.markdown("---")

    col_i1, col_i2, col_i3 = st.columns(3)
    with col_i1:
        st.markdown("""
        <div class="info-card">
            <h4 style="color:#1b5e20; margin-top:0;">① 自报+交叉验证</h4>
            <p style="font-size:0.9rem;">通过 <strong>自报面积 vs 补贴面积</strong> 交叉验证，识别申报造假，破解"客户说什么银行信什么"困境</p>
        </div>
        """, unsafe_allow_html=True)

    with col_i2:
        st.markdown("""
        <div class="info-card">
            <h4 style="color:#1b5e20; margin-top:0;">② 动态收入测算</h4>
            <p style="font-size:0.9rem;">基于 <strong>气象×价格×规模</strong> 三因子模型动态测算当年真实收入，比静态征信数据更精准</p>
        </div>
        """, unsafe_allow_html=True)

    with col_i3:
        st.markdown("""
        <div class="info-card">
            <h4 style="color:#1b5e20; margin-top:0;">③ 跨主体实体对齐</h4>
            <p style="font-size:0.9rem;">通过 <strong>身份证号+行政村</strong> 三级匹配策略，打通银行/补贴/气象跨主体数据，实现95%+数据打通率，破解涉农数据孤岛</p>
        </div>
        """, unsafe_allow_html=True)

    # ===== 底部 =====
    st.markdown(f"""
    <div class="footer">
        <p>{SYSTEM_FULL_NAME} · {COMPETITION} · {TRACK}</p>
        <p>{ORGANIZATION} © 2026</p>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
