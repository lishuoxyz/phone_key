@echo off
rem Run the test suite against the PWA protocol implementation.
rem Needs Node.js: set NODE_EXE to its full path if it is not on PATH.
setlocal
set "NODE_EXE=%~dp0..\..\..\tools\node\node.exe"
if exist "%NODE_EXE%" goto run
set "NODE_EXE=node"
where node >nul 2>nul
if errorlevel 1 (
  echo Node.js not found. Install it or set NODE_EXE.
  exit /b 2
)
:run
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo Python 3 not found.
  exit /b 2
)
%PY% "%~dp0run_all.py" --node "%NODE_EXE%" --adapter "%NODE_EXE% %~dp0adapters\js\run.mjs"
exit /b %ERRORLEVEL%
