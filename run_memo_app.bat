@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

cd /d "%~dp0"

:: Python이 설치되어 있는지 확인
python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo https://www.python.org/downloads/ 에서 Python을 설치한 후 다시 실행해주세요.
    pause
    exit /b 1
)

:: 가상환경이 없으면 생성
if not exist "venv\Scripts\activate.bat" (
    echo [설정] 가상환경을 생성합니다...
    python -m venv venv
    if errorlevel 1 (
        echo [오류] 가상환경 생성에 실패했습니다.
        pause
        exit /b 1
    )
)

:: 가상환경 활성화
call venv\Scripts\activate.bat

:: customtkinter 설치 여부 확인 후 설치
python -c "import customtkinter" >nul 2>&1
if errorlevel 1 (
    echo [설치] customtkinter 설치 중...
    pip install customtkinter
    if errorlevel 1 (
        echo [오류] customtkinter 설치에 실패했습니다.
        pause
        exit /b 1
    )
)

:: memit 패키지 설치 여부 확인 후 설치
python -c "import memit" >nul 2>&1
if errorlevel 1 (
    echo [설치] memit 패키지 설치 중...
    pip install -e .
    if errorlevel 1 (
        echo [오류] memit 패키지 설치에 실패했습니다.
        pause
        exit /b 1
    )
)

:: 앱 실행
echo [실행] Memit Memo App을 시작합니다...
python memo_app.py

endlocal
