# 1. Find the PID listening on port 8000
netstat -ano | findstr :8000

# 2. Kill the process (replace <PID> with the number from the last column above)
Stop-Process -Id <PID> -Force