Write-Host "Starting CipherLens Locally..." -ForegroundColor Cyan

# Start Backend
Write-Host "Starting FastAPI Backend on port 8080..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8080 --reload"

# Start Frontend
Write-Host "Installing Frontend Dependencies and Starting Next.js on port 3000..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd frontend; npm install; npm run dev"

Write-Host "All services started in separate windows!" -ForegroundColor Cyan
Write-Host "Frontend: http://localhost:3000"
Write-Host "Backend API: http://localhost:8080/docs"
