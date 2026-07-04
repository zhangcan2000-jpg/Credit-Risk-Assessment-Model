@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   农户信贷智能风险分层系统 V1.0
echo   2026年"数据要素x"大赛山东分赛
echo   青岛农商银行即墨支行
echo ============================================================
echo.
echo 正在启动系统...
echo 浏览器将自动打开 http://localhost:8501
echo 按 Ctrl+C 可停止服务
echo.
streamlit run "🏠_首页.py"
pause
