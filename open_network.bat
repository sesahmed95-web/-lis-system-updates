@echo off
chcp 65001 >nul
echo ===== Lab System - network check =====
echo.
echo 1) Opening firewall port 9090 (needs Administrator)...
netsh advfirewall firewall delete rule name="Lab System 9090" >nul 2>&1
netsh advfirewall firewall add rule name="Lab System 9090" dir=in action=allow protocol=TCP localport=9090 profile=any
echo.
echo 2) Is LabSystem running and listening on 9090?
netstat -ano | find ":9090" | find "LISTENING"
if errorlevel 1 echo    NOT LISTENING - start the program first (start_lab.bat)
echo.
echo 3) This PC addresses - use one of these on the other PCs:  http://IP:9090
ipconfig | find "IPv4"
echo.
pause
