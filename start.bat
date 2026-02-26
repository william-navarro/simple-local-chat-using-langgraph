@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

echo.
echo =====================================================
echo   LangGraph Chat - Setup e Inicializacao
echo =====================================================
echo.

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"
set "CONDA_ENV_NAME=langgraph-chat"

:: --- Localizar Anaconda / Miniconda ---
echo [0/5] Localizando Anaconda...

set "CONDA_SCRIPT="

for %%P in (
    "%USERPROFILE%\anaconda3\Scripts\conda.exe"
    "%USERPROFILE%\miniconda3\Scripts\conda.exe"
    "%LOCALAPPDATA%\anaconda3\Scripts\conda.exe"
    "%LOCALAPPDATA%\miniconda3\Scripts\conda.exe"
    "C:\anaconda3\Scripts\conda.exe"
    "C:\miniconda3\Scripts\conda.exe"
    "C:\ProgramData\anaconda3\Scripts\conda.exe"
    "C:\ProgramData\miniconda3\Scripts\conda.exe"
) do (
    if exist %%P (
        set "CONDA_SCRIPT=%%~P"
        goto :conda_found
    )
)

echo [ERRO] Anaconda ou Miniconda nao encontrado nos caminhos padrao.
echo        Verifique se o Anaconda esta instalado e tente novamente.
echo        Ou edite este arquivo e defina CONDA_SCRIPT manualmente.
pause
exit /b 1

:conda_found
echo     Conda encontrado em: %CONDA_SCRIPT%

:: Inicializar conda para uso no cmd
call "%CONDA_SCRIPT%" >nul 2>&1

:: Localizar o activate.bat do conda
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
        goto :conda_base_found
    )
)

:conda_base_found
echo     Base conda: %CONDA_BASE%

:: --- Verificar Node ---
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Node.js nao encontrado. Instale Node.js 18+ e tente novamente.
    pause
    exit /b 1
)

:: --- Criar estrutura de pastas ---
echo.
echo [1/5] Criando estrutura de pastas...

mkdir "%BACKEND%" 2>nul
mkdir "%FRONTEND%\src\components\chat" 2>nul
mkdir "%FRONTEND%\src\components\sidebar" 2>nul
mkdir "%FRONTEND%\src\components\ui" 2>nul
mkdir "%FRONTEND%\src\store" 2>nul
mkdir "%FRONTEND%\src\hooks" 2>nul
mkdir "%FRONTEND%\src\types" 2>nul
mkdir "%FRONTEND%\src\lib" 2>nul

echo     Pastas criadas com sucesso.

:: --- Copiar arquivos fonte (opcional) ---
echo.
echo [2/5] Copia de arquivos fonte
echo     Os arquivos devem estar na mesma pasta que este .bat
echo     com os seguintes nomes:
echo.
echo     Backend : main.py, graph.py, schemas.py, config.py
echo               requirements.txt, backend.env
echo     Frontend: package.json, vite.config.ts, tsconfig.json
echo               index.html, frontend.env, App.tsx, main.tsx
echo               index.css, types.index.ts, useChatStore.ts
echo               useStream.ts, useHealth.ts, api.ts
echo               ChatWindow.tsx, MessageList.tsx, MessageItem.tsx
echo               InputBar.tsx, Sidebar.tsx, ConversationItem.tsx
echo               DeleteDialog.tsx, alert-dialog.tsx
echo.
set /p COPY_FILES="Deseja copiar os arquivos agora? (s/n): "

if /i "%COPY_FILES%"=="s" (
    echo.
    echo     Copiando arquivos...

    :: Backend
    copy /y "%ROOT%main.py"              "%BACKEND%\main.py"                                     >nul 2>&1
    copy /y "%ROOT%graph.py"             "%BACKEND%\graph.py"                                    >nul 2>&1
    copy /y "%ROOT%schemas.py"           "%BACKEND%\schemas.py"                                  >nul 2>&1
    copy /y "%ROOT%config.py"            "%BACKEND%\config.py"                                   >nul 2>&1
    copy /y "%ROOT%requirements.txt"     "%BACKEND%\requirements.txt"                            >nul 2>&1
    copy /y "%ROOT%backend.env"          "%BACKEND%\.env"                                        >nul 2>&1

    :: Frontend raiz
    copy /y "%ROOT%package.json"         "%FRONTEND%\package.json"                               >nul 2>&1
    copy /y "%ROOT%vite.config.ts"       "%FRONTEND%\vite.config.ts"                             >nul 2>&1
    copy /y "%ROOT%tsconfig.json"        "%FRONTEND%\tsconfig.json"                              >nul 2>&1
    copy /y "%ROOT%index.html"           "%FRONTEND%\index.html"                                 >nul 2>&1
    copy /y "%ROOT%frontend.env"         "%FRONTEND%\.env"                                       >nul 2>&1

    :: Frontend src
    copy /y "%ROOT%App.tsx"              "%FRONTEND%\src\App.tsx"                                >nul 2>&1
    copy /y "%ROOT%main.tsx"             "%FRONTEND%\src\main.tsx"                               >nul 2>&1
    copy /y "%ROOT%index.css"            "%FRONTEND%\src\index.css"                              >nul 2>&1

    :: Frontend src/types
    copy /y "%ROOT%types.index.ts"       "%FRONTEND%\src\types\index.ts"                         >nul 2>&1

    :: Frontend src/store
    copy /y "%ROOT%useChatStore.ts"      "%FRONTEND%\src\store\useChatStore.ts"                  >nul 2>&1

    :: Frontend src/hooks
    copy /y "%ROOT%useStream.ts"         "%FRONTEND%\src\hooks\useStream.ts"                     >nul 2>&1
    copy /y "%ROOT%useHealth.ts"         "%FRONTEND%\src\hooks\useHealth.ts"                     >nul 2>&1

    :: Frontend src/lib
    copy /y "%ROOT%api.ts"               "%FRONTEND%\src\lib\api.ts"                             >nul 2>&1

    :: Frontend src/components/chat
    copy /y "%ROOT%ChatWindow.tsx"       "%FRONTEND%\src\components\chat\ChatWindow.tsx"          >nul 2>&1
    copy /y "%ROOT%MessageList.tsx"      "%FRONTEND%\src\components\chat\MessageList.tsx"         >nul 2>&1
    copy /y "%ROOT%MessageItem.tsx"      "%FRONTEND%\src\components\chat\MessageItem.tsx"         >nul 2>&1
    copy /y "%ROOT%InputBar.tsx"         "%FRONTEND%\src\components\chat\InputBar.tsx"            >nul 2>&1

    :: Frontend src/components/sidebar
    copy /y "%ROOT%Sidebar.tsx"          "%FRONTEND%\src\components\sidebar\Sidebar.tsx"          >nul 2>&1
    copy /y "%ROOT%ConversationItem.tsx" "%FRONTEND%\src\components\sidebar\ConversationItem.tsx" >nul 2>&1
    copy /y "%ROOT%DeleteDialog.tsx"     "%FRONTEND%\src\components\sidebar\DeleteDialog.tsx"     >nul 2>&1

    :: Frontend src/components/ui
    copy /y "%ROOT%alert-dialog.tsx"     "%FRONTEND%\src\components\ui\alert-dialog.tsx"         >nul 2>&1

    echo     Arquivos copiados com sucesso.
    echo.
    echo     ATENCAO: backend.env copiado para backend\.env
    echo              frontend.env copiado para frontend\.env
    echo              Confirme os valores antes de continuar.
    echo.
    pause
) else (
    echo     Copia ignorada. Certifique-se de que os arquivos ja estao
    echo     nas pastas corretas antes de prosseguir.
)

:: --- Conda: criar ambiente se nao existir ---
echo.
echo [3/5] Configurando ambiente conda...

call "%CONDA_BASE%\Scripts\activate.bat" "%CONDA_BASE%"

conda env list | findstr /C:"%CONDA_ENV_NAME%" >nul 2>&1
if errorlevel 1 (
    echo     Criando ambiente conda "%CONDA_ENV_NAME%" com Python 3.11...
    call conda create -n %CONDA_ENV_NAME% python=3.11 -y
    if errorlevel 1 (
        echo [ERRO] Falha ao criar ambiente conda.
        pause
        exit /b 1
    )
) else (
    echo     Ambiente "%CONDA_ENV_NAME%" ja existe, pulando criacao.
)

echo     Ativando ambiente e instalando dependencias Python...
call conda activate %CONDA_ENV_NAME%

cd /d "%BACKEND%"
pip install -r requirements.txt --quiet

if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias Python.
    pause
    exit /b 1
)

echo     Backend configurado com sucesso.

:: --- Frontend: instalar dependencias ---
echo.
echo [4/5] Configurando frontend Node.js...

cd /d "%FRONTEND%"

if not exist "node_modules" (
    echo     Instalando dependencias npm...
    npm install
    if errorlevel 1 (
        echo [ERRO] Falha ao instalar dependencias npm.
        pause
        exit /b 1
    )
) else (
    echo     node_modules ja existe, pulando npm install.
)

echo     Frontend configurado com sucesso.

:: --- Iniciar servidores ---
echo.
echo [5/5] Iniciando servidores...
echo.
echo     Backend:  http://localhost:8000
echo     Frontend: http://localhost:5173
echo     Docs API: http://localhost:8000/docs
echo.

start "LangGraph Chat - Backend" cmd /k "call "%CONDA_BASE%\Scripts\activate.bat" "%CONDA_BASE%" && conda activate %CONDA_ENV_NAME% && cd /d %BACKEND% && uvicorn main:app --reload --port 8000"

timeout /t 2 /nobreak >nul

start "LangGraph Chat - Frontend" cmd /k "cd /d %FRONTEND% && npm run dev"

timeout /t 3 /nobreak >nul
start "" "http://localhost:5173"

echo Ambos os servidores foram iniciados em janelas separadas.
echo Feche as janelas dos servidores para encerrar.
echo.
pause
endlocal
