@echo off
echo 부동산 자동 수집 스케줄러 시작 중...
cd /d %~dp0
pythonw scheduler.py >> logs\scheduler.log 2>&1
echo 스케줄러가 백그라운드에서 실행 중입니다.
pause
