@echo off
setlocal
chcp 65001 >nul

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"

where conda >nul 2>nul || (
  echo [ERROR] conda was not found in PATH.
  pause
  exit /b 1
)

where npm >nul 2>nul || (
  echo [ERROR] npm was not found in PATH.
  pause
  exit /b 1
)

if not exist "%ROOT%.env" (
  echo [ERROR] %ROOT%.env does not exist.
  pause
  exit /b 1
)

if not exist "%FRONTEND%\node_modules" (
  echo [ERROR] Frontend dependencies are missing. Run npm install in frontend first.
  pause
  exit /b 1
)

echo [1/6] Applying database migrations...
pushd "%BACKEND%"
call conda run -n drl alembic upgrade head
if errorlevel 1 (
  popd
  echo [ERROR] Database migration failed.
  pause
  exit /b 1
)
popd

echo [2/6] Starting Chroma...
start "ResearchForge - Chroma" cmd /k "cd /d ""%BACKEND%"" && conda run --no-capture-output -n drl python -m app.scripts.run_chroma"

echo [3/6] Starting parsing and general worker...
start "ResearchForge - Parse Worker" cmd /k "cd /d ""%BACKEND%"" && conda run --no-capture-output -n drl python -m app.scripts.run_worker paper_parse scheme_generate"

echo [4/6] Starting knowledge extraction worker...
start "ResearchForge - Knowledge Worker" cmd /k "cd /d ""%BACKEND%"" && conda run --no-capture-output -n drl python -m app.scripts.run_worker knowledge_extract"

echo [5/6] Starting API...
start "ResearchForge - API" cmd /k "cd /d ""%BACKEND%"" && conda run --no-capture-output -n drl uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

echo [6/6] Starting frontend...
start "ResearchForge - Frontend" cmd /k "cd /d ""%FRONTEND%"" && npm run dev"

echo.
echo ResearchForge is starting. Open http://localhost:5173
timeout /t 3 >nul
endlocal
