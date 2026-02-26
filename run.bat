@echo off
setlocal
chcp 65001 >nul

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"
set "CONDA_ENV_NAME=langgraph-chat"

:: Localizar base do conda
set "CONDA_BASE="
for %%P in (
    "%USERPROFILE%\anaconda3"
    "%USERPROFILE%\miniconda3"
    "%LOCALAPPDATA%\anaconda3"
    "%LOCALAPPDATA%\miniconda3"
    "C:\anaconda3"
    "C:\miniconda3"
    "C:\ProgramData\anaconda3"
    "C:\ProgramData\miniconda3"
) do (
    if exist "%%~P\Scripts\activate.bat" (
        set "CONDA_BASE=%%~P"
        goto :found
    )
)

echo [ERRO] Anaconda nao encontrado. Execute start.bat primeiro.
pause
exit /b 1

:found
echo.
echo =====================================================
echo   LangGraph Chat - Iniciando servidores
echo =====================================================
echo.
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:5173
echo   Docs API: http://localhost:8000/docs
echo.

start "LangGraph Chat - Backend" cmd /k "call "%CONDA_BASE%\Scripts\activate.bat" "%CONDA_BASE%" && conda activate %CONDA_ENV_NAME% && cd /d %BACKEND% && uvicorn main:app --reload --port 8000"

timeout /t 2 /nobreak >nul

start "LangGraph Chat - Frontend" cmd /k "cd /d %FRONTEND% && npm run dev"

timeout /t 3 /nobreak >nul
start "" "http://localhost:5173"

endlocal
