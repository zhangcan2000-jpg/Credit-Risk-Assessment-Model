"""
系统配置 - 农户信贷智能风险分层系统
"""
import os
from pathlib import Path

# ===== 路径配置 =====
SYSTEM_ROOT = Path(__file__).parent.parent
PROJECT_ROOT = SYSTEM_ROOT.parent
MODEL_DIR = PROJECT_ROOT / "models"
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
UPLOAD_DIR = SYSTEM_ROOT / "uploads"
HISTORY_DIR = SYSTEM_ROOT / "history"

# 创建必要目录
for d in [UPLOAD_DIR, HISTORY_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ===== 系统信息 =====
SYSTEM_NAME = "农户信贷智能风险分层系统"
SYSTEM_VERSION = "V1.0"
SYSTEM_FULL_NAME = f"{SYSTEM_NAME} {SYSTEM_VERSION}"

# 单位信息
ORGANIZATION = "青岛农商银行即墨支行"
DEVELOPER = "普惠部"
RESPONSIBLE = "杨京泽"

# 参赛信息
COMPETITION = "2026年\"数据要素×\"大赛山东分赛"
TRACK = "现代农业赛道"
PROJECT_NAME = "基于农户信贷多要素画像的涉农贷款风险分层模型研究"

# 风险阈值
RISK_THRESHOLDS = {
    "low": 0.20,
    "high": 0.50,
}

# 农作物配置
CROP_SUBSIDY_RATE = {
    "玉米": 80,
    "小麦": 110,
    "水稻": 150,
    "花生": 50,
    "蔬菜": 30,
    "果树": 40,
}

CROP_REVENUE_RATE = {
    "玉米": 800,
    "小麦": 900,
    "水稻": 1200,
    "花生": 1500,
    "蔬菜": 2500,
    "果树": 3000,
}
