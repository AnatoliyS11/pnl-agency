@echo off
cd /d "%~dp0"
echo Запускаю P&L дашборд агентства...
echo Откройте браузер по адресу: http://localhost:8501
echo Для остановки нажмите Ctrl+C
echo.
python -m streamlit run dashboard/app.py --server.port 8501
pause
