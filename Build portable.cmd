@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build-portable.ps1" %*
set "BuildResult=%ERRORLEVEL%"
echo.
if "%BuildResult%"=="0" (
    echo Build complete: "%~dp0artifacts\portable\Splicelet\Splicelet.exe"
) else (
    echo Build failed. See the messages above.
)
if /I not "%~1"=="-NoPause" pause
exit /b %BuildResult%
