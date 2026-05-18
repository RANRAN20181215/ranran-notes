@echo off
chcp 65001 >nul
echo ===== OpenCode 一键恢复 =====

echo 1/2 恢复项目配置...
cd /d "%~dp0.."
git pull
if %errorlevel% neq 0 (
    echo [!] git pull 失败，请检查网络或仓库
    pause
    exit /b
)

echo 2/2 恢复全局配置...
copy /Y "%~dp0global-config.backup.json" "%USERPROFILE%\.config\opencode\opencode.json"
if %errorlevel% neq 0 (
    echo [!] 全局配置恢复失败
    pause
    exit /b
)

echo ===== 全部恢复完成，请重启 OpenCode =====
pause
