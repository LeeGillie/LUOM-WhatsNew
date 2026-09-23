@echo off
rem ---------------------------------------------------------------------------
rem  Starts LUOM What's New (LUOM-WhatsNew.pyz in this folder) - a free,
rem  independent LUOM community tool that indexes and links to WeCreat's public
rem  knowledge base. LUOM does not maintain that knowledge base and is not
rem  affiliated with WeCreat.
rem
rem  Needs Python 3.8 or newer. If it is not installed, offers to install
rem  Python for the current user with winget (built into Windows 10/11, no
rem  administrator rights needed), and only after you say yes.
rem
rem  Any arguments are passed on, e.g.:  "Start LUOM What's New.cmd" scan
rem ---------------------------------------------------------------------------
setlocal EnableExtensions EnableDelayedExpansion
title LUOM What's New
set "APP=%~dp0LUOM-WhatsNew.pyz"
set "PYFILE=%TEMP%\luom-whatsnew-python.txt"

if not exist "%APP%" (
    echo LUOM-WhatsNew.pyz was not found next to this file:
    echo   %APP%
    echo Keep the two files together in the same folder.
    pause
    exit /b 1
)

call :findpython
if defined PYW goto :run

echo.
echo  LUOM What's New needs Python 3.8 or newer, and it was not found on this computer.
echo.
where winget >nul 2>nul
if errorlevel 1 goto :manual

echo  Python can be installed now for your user account only, using the Windows
echo  package manager (winget). No administrator rights are needed.
echo.
choice /C YN /M " Install Python 3.12 now"
if errorlevel 2 goto :manual

winget install --exact --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
call :findpython
if defined PYW goto :run
echo.
echo  Python was installed but could not be found yet. Close this window and
echo  double-click "Start LUOM What's New" again.
pause
exit /b 1

:manual
echo.
echo  Please install Python from https://www.python.org/downloads/
echo  (the default options are fine), then double-click "Start LUOM What's New" again.
echo.
start "" "https://www.python.org/downloads/"
pause
exit /b 1

:run
rem A scan is run in this window so its output stays visible; the UI runs
rem windowless and is stopped with the power button on the page.
if /i "%~1"=="scan" (
    "!PYEXE!" "%APP%" %*
    exit /b !errorlevel!
)
start "" "!PYW!" "%APP%" %*
exit /b 0


rem ---------------------------------------------------------------------------
rem  :findpython - sets PYEXE (python.exe) and PYW (pythonw.exe) if a usable
rem  Python 3.8+ exists. Tries the py launcher, PATH, then the default
rem  per-user install folders (PATH is not refreshed right after winget).
rem ---------------------------------------------------------------------------
:findpython
set "PYW="
set "PYEXE="
call :try py -3
if defined PYW exit /b 0
call :try python
if defined PYW exit /b 0
if exist "%LOCALAPPDATA%\Programs\Python\Launcher\py.exe" call :try "%LOCALAPPDATA%\Programs\Python\Launcher\py.exe" -3
if defined PYW exit /b 0
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if not defined PYW if exist "%%~D\python.exe" call :try "%%~D\python.exe"
)
exit /b 0

:try
if exist "%PYFILE%" del "%PYFILE%" >nul 2>nul
%* -c "import sys, os; d = os.path.dirname(sys.executable); print(sys.executable if sys.version_info >= (3, 8) else ''); print(os.path.join(d, 'pythonw.exe'))" > "%PYFILE%" 2>nul
if not exist "%PYFILE%" exit /b 0
set "CAND_EXE="
set "CAND_W="
< "%PYFILE%" (
    set /p "CAND_EXE="
    set /p "CAND_W="
)
del "%PYFILE%" >nul 2>nul
if not defined CAND_EXE exit /b 0
if not exist "!CAND_EXE!" exit /b 0
set "PYEXE=!CAND_EXE!"
if exist "!CAND_W!" (set "PYW=!CAND_W!") else (set "PYW=!CAND_EXE!")
exit /b 0
