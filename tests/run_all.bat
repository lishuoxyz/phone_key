@echo off
rem phone_key test suite (ASCII only: cmd parses .bat with the OEM code page)
setlocal
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo Python 3 not found. Install Python 3 or run with the ESP-IDF python.
  exit /b 2
)
%PY% "%~dp0run_all.py" %*
exit /b %ERRORLEVEL%
