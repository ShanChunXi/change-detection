@echo off

setlocal enabledelayedexpansion



REM ============================================================

REM  Change Detection Launcher

REM  SuperMap Cup

REM ============================================================

REM

REM  Usage:

REM    Double-click  ->  interactive menu

REM    run.bat check ->  environment check

REM    run.bat run --before ... --after ... --out ...

REM

REM  First-time users: if Python is not found, this script will

REM  guide you through configuration interactively -- no manual

REM  JSON editing needed.

REM ============================================================



set "SCRIPT=%~dp0src\change_detection.py"

set "CONFIG=%~dp0src\config.json"



REM --- Try to find SuperMap Python ---

set "PY="



REM 1) From config.json (extract python_path via findstr)

if exist "%CONFIG%" (

    for /f "tokens=2 delims=: " %%a in (

        'findstr "python_path" "%CONFIG%"'

    ) do (

        set "RAW=%%~a"

        set "RAW=!RAW:"=!"

        set "RAW=!RAW:,=!"

        if exist "!RAW!" set "PY=!RAW!"

    )

)



REM 2) Fallback: default SuperMap installation path

if "%PY%"=="" (

    if exist "F:\supermap\supermap-iobjectspy-env-gpu-2026-win64\conda\python.exe" (

        set "PY=F:\supermap\supermap-iobjectspy-env-gpu-2026-win64\conda\python.exe"

    )

)



REM 3) Fallback: use whatever python is in PATH

if "%PY%"=="" (

    where python >nul 2>&1

    if not errorlevel 1 (

        set "PY=python"

    )

)



REM --- Verify any Python found above can actually import iobjectspy ---

if not "%PY%"=="" (

    "%PY%" -c "import iobjectspy" >nul 2>&1

    if errorlevel 1 (

        echo.

        echo  [WARN] 找到的 Python 无法导入 iobjectspy，不是超图 Python

        echo         %PY%

        echo         下面进入交互式配置...

        set "PY="

    )

)



REM --- If Python found AND verified, skip interactive setup ---

if not "%PY%"=="" goto :launch



REM ============================================================

REM  Step 1: Find Python

REM ============================================================

:interactive_setup

echo.

echo  +==========================================================+

echo  ^|        SuperMap Python 环境未找到                        ^|

echo  ^|        请按提示完成首次配置                              ^|

echo  +==========================================================+

echo.

echo  请将 SuperMap iObjects Python 的安装目录拖入此窗口，

echo  或手动输入 python.exe 的完整路径。

echo.

echo    示例目录: F:\supermap\supermap-iobjectspy-env-gpu-2026-win64

echo    示例文件: F:\supermap\...\conda\python.exe

echo.

echo    直接按回车 - 使用系统 PATH 中的 python

echo.

set /p "USER_INPUT=  ^> "



REM --- User pressed Enter without input - use PATH python ---

if "!USER_INPUT!"=="" (

    echo.

    echo  [WARN] 未输入，使用系统 PATH 中的 python

    set "PY=python"

    "%PY%" -c "import iobjectspy" >nul 2>&1

    if errorlevel 1 (

        echo  [ERROR] PATH 中的 python 不是 SuperMap Python，无法导入 iobjectspy。

        echo         请将超图 Python 安装目录拖入此窗口，或手动输入完整路径

        echo.

        goto :interactive_setup

    )

    echo  [OK] 验证通过，确认为超图 Python

    set "CFG_PYTHON=python"

    goto :configure_java_home

)



REM Strip surrounding quotes (from drag-and-drop)

set "USER_INPUT=!USER_INPUT:"=!"



REM Strip trailing backslash

if "!USER_INPUT:~-1!"=="\" set "USER_INPUT=!USER_INPUT:~0,-1!"



echo.

echo  正在查找 python.exe ...



set "PY_FOUND="



REM a) Input is the python.exe file itself

echo !USER_INPUT! | findstr /i "python.exe" >nul

if !errorlevel!==0 if exist "!USER_INPUT!" (

    set "PY_FOUND=!USER_INPUT!"

)



REM b) Input is a directory containing python.exe

if "!PY_FOUND!"=="" if exist "!USER_INPUT!\python.exe" (

    set "PY_FOUND=!USER_INPUT!\python.exe"

)



REM c) conda/python.exe (SuperMap typical layout)

if "!PY_FOUND!"=="" if exist "!USER_INPUT!\conda\python.exe" (

    set "PY_FOUND=!USER_INPUT!\conda\python.exe"

)



REM d) bin/python.exe

if "!PY_FOUND!"=="" if exist "!USER_INPUT!\bin\python.exe" (

    set "PY_FOUND=!USER_INPUT!\bin\python.exe"

)



REM e) Recursive search (slower, last resort)

if "!PY_FOUND!"=="" if exist "!USER_INPUT!\" (

    for /r "!USER_INPUT!" %%f in (python.exe) do (

        if "!PY_FOUND!"=="" set "PY_FOUND=%%f"

    )

)



REM --- Not found - retry ---

if "!PY_FOUND!"=="" (

    echo.

    echo  [ERROR] 在指定位置未找到 python.exe：

    echo           !USER_INPUT!

    echo.

    echo  请确认路径是否正确，然后重试。

    goto :interactive_setup

)



REM --- Verify this is really SuperMap Python ---

"!PY_FOUND!" -c "import iobjectspy" >nul 2>&1

if errorlevel 1 (

    echo.

    echo  [ERROR] 该 Python 无法导入 iobjectspy，不是超图 Python：

    echo           !PY_FOUND!

    echo.

    echo  请确保选择了 SuperMap iObjects Python 的安装目录

    echo  （通常是包含 conda/python.exe 的目录）

    echo.

    goto :interactive_setup

)



echo.

echo  [OK] 找到: !PY_FOUND!

echo  [OK] 已验证为超图 Python（iobjectspy 导入成功）



set "CFG_PYTHON=!PY_FOUND:\=/!"

set "PY=!PY_FOUND!"



REM ============================================================

REM  Step 2: Configure java_home

REM ============================================================

:configure_java_home

echo.

echo  +==========================================================+

echo  ^|  配置 java_home — SuperMap iObjects Java JRE 路径        ^|

echo  +==========================================================+

echo.

echo  请输入 SuperMap iObjects Java 的 JRE 目录：

echo    示例: F:\supermap\supermap-iobjectsjava-2026-win-all\jre1.8_x64

echo.

echo    直接按回车 - 跳过（可以以后配置）

echo.

set /p "USER_INPUT=  ^> "



if "!USER_INPUT!"=="" (

    echo  [INFO] 已跳过 java_home 配置

    set "CFG_JAVA="

    goto :configure_iobjects_bin

)



set "USER_INPUT=!USER_INPUT:"=!"

if "!USER_INPUT:~-1!"=="\" set "USER_INPUT=!USER_INPUT:~0,-1!"



if not exist "!USER_INPUT!\" (

    echo  [ERROR] 目录不存在: !USER_INPUT!

    echo  请确认路径后重试。

    goto :configure_java_home

)



set "CFG_JAVA=!USER_INPUT:\=/!"

echo  [OK] java_home: !CFG_JAVA!



REM ============================================================

REM  Step 3: Configure iobjects_bin

REM ============================================================

:configure_iobjects_bin

echo.

echo  +==========================================================+

echo  ^|  配置 iobjects_bin — SuperMap iObjects Java Bin 路径     ^|

echo  +==========================================================+

echo.

echo  请输入 SuperMap iObjects Java 的 Bin 目录：

echo    示例: F:\supermap\supermap-iobjectsjava-2026-win-all\Bin

echo.

echo    直接按回车 - 跳过（可以以后配置）

echo.

set /p "USER_INPUT=  ^> "



if "!USER_INPUT!"=="" (

    echo  [INFO] 已跳过 iobjects_bin 配置

    set "CFG_IOBJECTS="

    goto :configure_resources_ml

)



set "USER_INPUT=!USER_INPUT:"=!"

if "!USER_INPUT:~-1!"=="\" set "USER_INPUT=!USER_INPUT:~0,-1!"



if not exist "!USER_INPUT!\" (

    echo  [ERROR] 目录不存在: !USER_INPUT!

    echo  请确认路径后重试。

    goto :configure_iobjects_bin

)



set "CFG_IOBJECTS=!USER_INPUT:\=/!"

echo  [OK] iobjects_bin: !CFG_IOBJECTS!



REM ============================================================

REM  Step 4: Configure resources_ml

REM ============================================================

:configure_resources_ml

echo.

echo  +==========================================================+

echo  ^|  配置 resources_ml — SuperMap ML 模型资源路径            ^|

echo  +==========================================================+

echo.

echo  请输入 SuperMap ML 资源包目录（内含 model 文件夹）：

echo    示例: F:\supermap\supermap-iobjectspy-resources_ml-2025u1\resources_ml

echo.

echo    直接按回车 - 跳过（可以以后配置）

echo.

set /p "USER_INPUT=  ^> "



if "!USER_INPUT!"=="" (

    echo  [INFO] 已跳过 resources_ml 配置

    set "CFG_RESOURCES="

    goto :save_all_config

)



set "USER_INPUT=!USER_INPUT:"=!"

if "!USER_INPUT:~-1!"=="\" set "USER_INPUT=!USER_INPUT:~0,-1!"



if not exist "!USER_INPUT!\" (

    echo  [ERROR] 目录不存在: !USER_INPUT!

    echo  请确认路径后重试。

    goto :configure_resources_ml

)



set "CFG_RESOURCES=!USER_INPUT:\=/!"

echo  [OK] resources_ml: !CFG_RESOURCES!



REM ============================================================

REM  Save all paths to config.json

REM ============================================================

:save_all_config

echo.

echo  +==========================================================+

echo  ^|  正在保存配置...                                         ^|

echo  +==========================================================+



REM Write config.json via PowerShell

powershell -NoProfile -Command "@{java_home='!CFG_JAVA!'; iobjects_bin='!CFG_IOBJECTS!'; resources_ml='!CFG_RESOURCES!'; python_path='!CFG_PYTHON!'} | ConvertTo-Json -Depth 4 | Set-Content '%CONFIG%'" 2>nul



REM Fallback: if PowerShell failed, create config.json manually

if errorlevel 1 (

    > "%CONFIG%" echo {

    >>"%CONFIG%" echo     "java_home": "!CFG_JAVA!",

    >>"%CONFIG%" echo     "iobjects_bin": "!CFG_IOBJECTS!",

    >>"%CONFIG%" echo     "resources_ml": "!CFG_RESOURCES!",

    >>"%CONFIG%" echo     "python_path": "!CFG_PYTHON!"

    >>"%CONFIG%" echo }

)



echo.

echo  [OK] 配置已保存到 config.json

echo.

echo  +==========================================================+

echo  ^|  配置摘要:                                               ^|

echo  +==========================================================+

echo    python_path  : !CFG_PYTHON!

echo    java_home    : !CFG_JAVA!

echo    iobjects_bin : !CFG_IOBJECTS!

echo    resources_ml : !CFG_RESOURCES!

echo  +==========================================================+



REM --- Check for missing paths ---

set "MISSING="

if "!CFG_JAVA!"=="" set "MISSING=!MISSING! java_home"

if "!CFG_IOBJECTS!"=="" set "MISSING=!MISSING! iobjects_bin"

if "!CFG_RESOURCES!"=="" set "MISSING=!MISSING! resources_ml"



if not "!MISSING!"=="" (

    echo.

    echo  [WARN] 以下路径未配置:!MISSING!

    echo         可在菜单中选 [6] 配置向导 补充，不影响基本使用

)



REM --- Offer to run environment check ---

echo.

echo  是否运行环境自检？

echo    [Y] 是，检查配置是否正确（推荐）

echo    [N] 否，直接启动

echo.

set /p "RUN_CHECK=  ^> "

if /i "!RUN_CHECK!"=="y" (

    echo.

    "%PY%" "%SCRIPT%" check

    echo.

    echo  +==========================================================+

    echo  ^|  自检完成，将自动进入主菜单...                          ^|

    echo  +==========================================================+

    timeout /t 2 /nobreak >nul

    goto :launch

)



REM ============================================================

REM  Launch

REM ============================================================

:launch

if not exist "%SCRIPT%" (

    echo [ERROR] Script not found: %SCRIPT%

    pause

    exit /b 1

)



if "%~1"=="" (
    "%PY%" "%SCRIPT%" menu
) else (
    "%PY%" "%SCRIPT%" %*
)
pause

