@echo off
chcp 65001 >nul
docker exec --workdir /home/pwuser/workspace/bigdata-collection-labs-112404260129/lab02/part2_collection smartpark-student-course-workspace-1 python browser_collect.py
set "COLLECT_EXIT=%ERRORLEVEL%"
echo.
if not "%COLLECT_EXIT%"=="0" echo [ERROR] Collection stopped. See evidence/browser_runs for the actual error.
pause
exit /b %COLLECT_EXIT%
