@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo PatentBase を起動しています...

REM サーバーを別ウィンドウで起動
start "PatentBase Server" cmd /k "uv run uvicorn backend.app.main:app --port 8765"

REM サーバーの起動を待機（3秒）
timeout /t 3 /nobreak > nul

REM ブラウザを開く
start "" "http://localhost:8765"

echo.
echo サーバーが起動しました: http://localhost:8765
echo サーバーを停止するには「PatentBase Server」ウィンドウを閉じてください。
