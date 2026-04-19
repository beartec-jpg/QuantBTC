@echo off
setlocal
set SCRIPT_DIR=%~dp0
where pwsh >nul 2>nul
if %ERRORLEVEL%==0 (
  pwsh -ExecutionPolicy Bypass -File "%SCRIPT_DIR%qbtc-testnet-windows.ps1" %*
) else (
  powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%qbtc-testnet-windows.ps1" %*
)
endlocal
