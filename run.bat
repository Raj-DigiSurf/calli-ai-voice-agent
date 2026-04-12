@echo off
echo =========================================
echo  Dalliance AI Receptionist - Start All
echo =========================================
echo.

REM Start mock booking page on port 8080
echo Starting mock booking page on port 8080...
start "Mock Booking Page" python -m http.server 8080 --directory mock-booking

REM Wait a moment then start FastAPI
timeout /t 2 /nobreak >nul

echo Starting FastAPI server on port 8000...
start "FastAPI Server" cmd /k "cd server && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

REM Wait for FastAPI to start
timeout /t 4 /nobreak >nul

echo.
echo Starting ngrok tunnel (needed for Vapi to reach your server)...
echo.
echo If ngrok is installed, run in a NEW terminal:
echo   ngrok http 8000
echo Then paste the https URL into:
echo   python server\update_webhook.py ^<your-ngrok-url^>
echo.
echo =========================================
echo  Services running:
echo  Mock page: http://localhost:8080
echo  API:       http://localhost:8000
echo  Bookings:  http://localhost:8000/bookings
echo =========================================
echo.
echo Call +1 (641) 401-8386 to test the voice agent
echo (requires ngrok tunnel to be active)
echo.
pause
