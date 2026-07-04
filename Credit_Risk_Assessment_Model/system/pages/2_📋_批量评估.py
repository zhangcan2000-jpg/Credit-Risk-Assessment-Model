"""
批量评估页面
==================================
CSV上传 → 批量评估 → 结果下载
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
from datetime import datetime
import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="批量评估 - 农户信贷智能风险分层系统",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

from core.predictor import predict_batch
from core.config import UPLOAD_DIR, HISTORY_DIR


# CSV 模板列名（中文） → 内部字段名（英文）
COLUMN_MAP = {
    "姓名": "name",
    "身份证尾号": "id_tail",
    "年龄": "age",
    "性别": "gender",
    "婚姻状况": "marital",
    "受教育程度": "education",
    "种植作物": "crop",
    "真实种植面积(亩)": "true_area",
    "自报种植面积(亩)": "reported_area",
    "补贴种植面积(亩)": "subsidy_area",
    "补贴稳定领取": "subsidy_stable",
    "当年是否灾害": "is_drought_year",
    "是否种植大棚": "has_greenhouse",
    "气象年景评分": "weather_score",
    "农产品价格同比": "price_change",
    "测算真实年收入(元)": "true_income",
    "自报年收入(元)": "reported_income",
    "申请贷款金额(元)": "loan_amount",
    "贷款期限(月)": "loan_term",
    "是否有其他贷款": "has_other_loan",
    "近两年累计逾期次数": "overdue_count_history",
    "近两年最长连续逾期次数": "consecutive_overdue",
    "家庭总资产(元)": "total_assets",
    "家庭总负债(元)": "total_liabilities",
}

# 必填字段（内部英文名）
REQUIRED_COLS = [
    "age", "gender", "marital", "education", "crop",
    "true_area", "reported_area", "subsidy_area",
    "subsidy_stable", "is_drought_year", "has_greenhouse",
    "weather_score", "price_change", "true_income", "reported_income",
    "loan_amount", "loan_term", "has_other_loan", "overdue_count_history",
]


def main():
    st.markdown("# 📋 批量风险评估")
    st.caption("上传农户信息CSV文件，系统批量评估并生成报告")

    # 本地化 file_uploader 的英文文案（Streamlit 1.55 默认英文）
    st.markdown("""
    <style>
    [data-testid="stFileUploaderDropzone"] span,
    [data-testid="stFileUploaderDropzone"] small,
    [data-testid="stFileUploaderDropzone"] button {
        font-size: 0 !important;
    }
    [data-testid="stFileUploaderDropzone"] > div > div > span::after {
        content: "将文件拖拽到此处";
        font-size: 14px;
        font-weight: 600;
    }
    [data-testid="stFileUploaderDropzone"] small::after {
        content: "单个文件最大 200MB";
        font-size: 12px;
        color: #888;
    }
    [data-testid="stFileUploaderDropzone"] button::before {
        content: "选择文件";
        font-size: 14px;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("---")

    # ===== 下载模板 =====
    st.markdown("### 📥 第一步：下载模板")
    st.markdown("请按模板格式填写农户信息：")

    template_data = pd.DataFrame([
        {
            "姓名": "张三", "身份证尾号": "***1234",
            "年龄": 45, "性别": "男", "婚姻状况": "已婚", "受教育程度": "初中",
            "种植作物": "玉米", "真实种植面积(亩)": 30, "自报种植面积(亩)": 30, "补贴种植面积(亩)": 30,
            "补贴稳定领取": "是", "当年是否灾害": "否", "是否种植大棚": "否",
            "气象年景评分": 0.85, "农产品价格同比": 0.0,
            "测算真实年收入(元)": 24000, "自报年收入(元)": 24000,
            "申请贷款金额(元)": 20000, "贷款期限(月)": 12,
            "是否有其他贷款": "否", "近两年累计逾期次数": 0, "近两年最长连续逾期次数": 0,
            "家庭总资产(元)": 300000, "家庭总负债(元)": 50000,
        },
        {
            "姓名": "李四", "身份证尾号": "***5678",
            "年龄": 52, "性别": "男", "婚姻状况": "已婚", "受教育程度": "高中/中专",
            "种植作物": "小麦", "真实种植面积(亩)": 80, "自报种植面积(亩)": 120, "补贴种植面积(亩)": 75,
            "补贴稳定领取": "否", "当年是否灾害": "是", "是否种植大棚": "否",
            "气象年景评分": 0.55, "农产品价格同比": -0.15,
            "测算真实年收入(元)": 60000, "自报年收入(元)": 95000,
            "申请贷款金额(元)": 50000, "贷款期限(月)": 24,
            "是否有其他贷款": "是", "近两年累计逾期次数": 3, "近两年最长连续逾期次数": 0,
            "家庭总资产(元)": 200000, "家庭总负债(元)": 80000,
        },
    ])
    st.download_button(
        label="📥 下载CSV模板",
        data=template_data.to_csv(index=False).encode("utf-8-sig"),
        file_name="农户信息模板.csv",
        mime="text/csv",
    )

    st.markdown("---")

    # ===== 上传区 =====
    st.markdown("### 📤 第二步：上传农户数据")
    uploaded_file = st.file_uploader("选择CSV文件", type=["csv"], label_visibility="collapsed")

    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
            st.success(f"✅ 文件上传成功，共 {len(df)} 条记录")

            # 中文列名 → 英文 key（兼容中英文模板）
            rename_dict = {cn: COLUMN_MAP[cn] for cn in df.columns if cn in COLUMN_MAP}
            if rename_dict:
                df = df.rename(columns=rename_dict)

            st.markdown("**数据预览：**")
            st.dataframe(df.head(5), use_container_width=True, hide_index=True)

            # 字段校验
            reverse_map = {v: k for k, v in COLUMN_MAP.items()}
            missing = [c for c in REQUIRED_COLS if c not in df.columns]
            if missing:
                cn_missing = [reverse_map.get(c, c) for c in missing]
                st.error(f"⚠️ 缺少必要字段：{', '.join(cn_missing)}")
                st.stop()

            # 补充默认值
            for col in ["name", "id_tail", "consecutive_overdue", "total_assets", "total_liabilities"]:
                if col not in df.columns:
                    df[col] = 0 if col not in ("name", "id_tail") else ""

            st.markdown("---")
            if st.button("🚀 开始批量评估", type="primary", use_container_width=True):
                with st.spinner(f"正在批量评估 {len(df)} 条记录..."):
                    records = df.to_dict(orient="records")
                    results = predict_batch(records)

                if not results:
                    st.error("评估失败")
                    st.stop()

                # 构造结果DataFrame
                result_df = pd.DataFrame([
                    {
                        "客户姓名": r["name"],
                        "身份证尾号": r["id_tail"],
                        "种植作物": r["crop"],
                        "种植面积(亩)": r["true_area"],
                        "是否大棚": r.get("has_greenhouse", "否"),
                        "违约概率": f"{r['probability']:.2%}",
                        "风险等级": r["tier"],
                        "建议措施": get_action_summary(r["tier"]),
                    }
                    for r in results
                ])

                # 保存到历史
                save_batch_history(results)

                st.markdown("---")
                st.markdown("### 📊 评估结果")
                st.markdown(f"共完成 **{len(results)}** 户评估")

                # 汇总统计
                tier_count = result_df["风险等级"].value_counts().reindex(["低风险", "中风险", "高风险", "拒贷"]).fillna(0)
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.metric("✅ 低风险", f"{int(tier_count.get('低风险', 0))} 户")
                with c2:
                    st.metric("⚠️ 中风险", f"{int(tier_count.get('中风险', 0))} 户")
                with c3:
                    st.metric("🚨 高风险", f"{int(tier_count.get('高风险', 0))} 户")
                with c4:
                    st.metric("⛔ 拒贷", f"{int(tier_count.get('拒贷', 0))} 户")

                st.markdown("**详细结果：**")
                st.dataframe(result_df, use_container_width=True, hide_index=True)

                # 下载结果
                st.markdown("---")
                st.markdown("### 💾 下载评估报告")
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    st.download_button(
                        label="📄 下载 CSV 报告",
                        data=result_df.to_csv(index=False).encode("utf-8-sig"),
                        file_name=f"风险评估报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )
                with col_d2:
                    # 完整数据：用中文列名（反向映射英文 key）
                    en_to_cn = {en: cn for cn, en in COLUMN_MAP.items()}
                    df_cn = df.rename(columns={
                        en: en_to_cn[en] for en in df.columns if en in en_to_cn
                    })
                    df_cn["违约概率"] = [f"{r['probability']:.2%}" for r in results]
                    df_cn["风险等级"] = [r["tier"] for r in results]
                    df_cn["资产负债率(LTV)"] = [
                        f"{r['ltv']:.0%}" if r.get("ltv") is not None else "-"
                        for r in results
                    ]
                    df_cn["建议措施"] = [get_action_summary(r["tier"]) for r in results]
                    st.download_button(
                        label="📊 下载完整数据 (含原始字段)",
                        data=df_cn.to_csv(index=False).encode("utf-8-sig"),
                        file_name=f"风险评估完整数据_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )

        except Exception as e:
            st.error(f"⚠️ 处理文件失败：{str(e)}")


def get_action_summary(tier):
    return {
        "低风险": "纯信用贷 + 利率优惠 + 绿色通道",
        "中风险": "担保增信 + 分批放款 + 月度监测",
        "高风险": "限额管理 + 人工复核 + 拒贷或压缩",
        "拒贷": "拒贷（连三累六）+ 进入灰名单",
    }.get(tier, "")


def save_batch_history(results):
    """保存批量评估历史"""
    history_file = HISTORY_DIR / "batch_history.json"
    history = []
    if history_file.exists():
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []

    summary = {"低风险": 0, "中风险": 0, "高风险": 0, "拒贷": 0}
    for r in results:
        summary[r["tier"]] += 1

    history.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(results),
        "summary": summary,
    })
    history = history[-50:]

    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
