@echo off
rem Installs, updates and starts the MRI TogetherThon's environment in Docker,
rem and opens JupyterLab in the browser. Double-click it; run it again to take
rem a newer image. Your work lives in %USERPROFILE%\mritogetherthon
rem (MRITOGETHERTHON_WORK names another folder), which is the home folder you
rem see in JupyterLab, so that it outlives the container and every update.
rem Run so, it also copies itself to %USERPROFILE%\.mritogetherthon and
rem registers that copy as the handler of mritogetherthon: links, which the hub
rem page's "Open JupyterLab" button opens.
setlocal
if "%MRITOGETHERTHON_IMAGE%"=="" (set "IMAGE=ghcr.io/mcencini/mritogetherthon") else (set "IMAGE=%MRITOGETHERTHON_IMAGE%")
set "NAME=mritogetherthon"
if "%MRITOGETHERTHON_PORT%"=="" (set "PORT=8899") else (set "PORT=%MRITOGETHERTHON_PORT%")
if "%MRITOGETHERTHON_HOME%"=="" (set "HOME_DIR=%USERPROFILE%\.mritogetherthon") else (set "HOME_DIR=%MRITOGETHERTHON_HOME%")
if "%MRITOGETHERTHON_WORK%"=="" (set "WORK=%USERPROFILE%\mritogetherthon") else (set "WORK=%MRITOGETHERTHON_WORK%")

where docker >nul 2>&1
if errorlevel 1 (
    echo Docker is not installed: install it from https://docs.docker.com/get-started/get-docker/ and run this again.
    goto :failed
)
call docker info >nul 2>&1
if errorlevel 1 (
    echo Docker is installed but not running: start Docker Desktop and run this again.
    goto :failed
)

if not exist "%HOME_DIR%" mkdir "%HOME_DIR%"
if not exist "%WORK%" mkdir "%WORK%"
set "LINK=%~1"
if not "%LINK%"=="" goto :token
if /i not "%~f0"=="%HOME_DIR%\mritogetherthon.bat" copy /y "%~f0" "%HOME_DIR%\mritogetherthon.bat" >nul
reg add "HKCU\Software\Classes\mritogetherthon" /ve /d "URL:mritogetherthon" /f >nul
reg add "HKCU\Software\Classes\mritogetherthon" /v "URL Protocol" /d "" /f >nul
reg add "HKCU\Software\Classes\mritogetherthon\shell\open\command" /ve /d "\"%HOME_DIR%\mritogetherthon.bat\" \"%%1\"" /f >nul
echo The hub page's Open JupyterLab button now starts the environment.

:token
rem The token JupyterLab asks for, made once and kept, so that a bookmark of
rem JupyterLab's address keeps working.
if not exist "%HOME_DIR%\token" powershell -NoProfile -Command "[guid]::NewGuid().ToString('N') | Set-Content -NoNewline -Encoding ascii '%HOME_DIR%\token'"
set /p TOKEN=<"%HOME_DIR%\token"

set "BEFORE="
for /f "delims=" %%i in ('docker image inspect --format "{{.Id}}" %IMAGE% 2^>nul') do set "BEFORE=%%i"
if "%BEFORE%"=="" (echo The environment is not installed: downloading %IMAGE% ^(several GB, once^).) else (echo The environment is installed: checking for a newer version.)
call docker pull %IMAGE%
if errorlevel 1 (
    if "%BEFORE%"=="" (
        echo The environment could not be downloaded.
        goto :failed
    )
    echo The newest version could not be checked: starting the installed one.
)
set "AFTER="
for /f "delims=" %%i in ('docker image inspect --format "{{.Id}}" %IMAGE% 2^>nul') do set "AFTER=%%i"
if "%BEFORE%"=="" (
    echo The environment is installed.
) else if "%BEFORE%"=="%AFTER%" (
    echo The environment is up to date.
) else (
    echo The environment was outdated and is updated.
)

rem A container already running the newest image is left as it is, so that the
rem notebooks' kernels keep running; any other is made again, with the work kept.
set "RUNNING="
for /f "delims=" %%i in ('docker inspect --format "{{.State.Running}} {{.Image}}" %NAME% 2^>nul') do set "RUNNING=%%i"
if "%RUNNING%"=="true %AFTER%" (
    echo The environment is already running.
    goto :wait
)
set "DIGEST="
for /f "delims=" %%i in ('docker image inspect --format "{{index .RepoDigests 0}}" %IMAGE% 2^>nul') do set "DIGEST=%%i"
call docker rm -f %NAME% >nul 2>&1
call docker run -d --restart unless-stopped --name %NAME% -p 127.0.0.1:%PORT%:8888 -e "JUPYTER_TOKEN=%TOKEN%" -e "MRITOGETHERTHON_IMAGE=%DIGEST%" -v "%WORK%:/home/mri" %IMAGE% >nul
if errorlevel 1 goto :failed
echo The environment is running, with your work in %WORK%.

:wait
set "URL=http://127.0.0.1:%PORT%/lab?token=%TOKEN%"
set /a TRIES=0
:poll
call curl -fs -o nul "http://127.0.0.1:%PORT%/api" >nul 2>&1
if not errorlevel 1 goto :open
set /a TRIES+=1
if %TRIES% gtr 60 (
    echo JupyterLab does not answer: see  docker logs %NAME%
    goto :failed
)
timeout /t 2 /nobreak >nul
goto :poll

:open
echo JupyterLab: %URL%
if "%MRITOGETHERTHON_NO_BROWSER%"=="" start "" "%URL%"
if "%LINK%"=="" pause
exit /b 0

:failed
pause
exit /b 1
