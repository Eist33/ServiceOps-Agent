@echo off
set LOG=D:\ServiceOps Agent\zdiag.txt
echo ===WHERE=== > "%LOG%"
where git >> "%LOG%" 2>&1
where bash >> "%LOG%" 2>&1
where sh >> "%LOG%" 2>&1
echo ===VER=== >> "%LOG%"
git --version >> "%LOG%" 2>&1
echo ===GITCMD=== >> "%LOG%"
D:\Git\cmd\git.exe --version >> "%LOG%" 2>&1
echo ===GITMINGW=== >> "%LOG%"
D:\Git\mingw64\bin\git.exe --version >> "%LOG%" 2>&1
echo ===FILES=== >> "%LOG%"
dir /b D:\Git\usr\bin\bash.exe >> "%LOG%" 2>&1
dir /b D:\Git\usr\bin\sh.exe >> "%LOG%" 2>&1
dir /b D:\Git\bin\bash.exe >> "%LOG%" 2>&1
dir /b D:\Git\cmd\git.exe >> "%LOG%" 2>&1
dir /b D:\Git\mingw64\bin\git.exe >> "%LOG%" 2>&1
dir /b D:\Git\usr\bin\git.exe >> "%LOG%" 2>&1
echo ===USRDIR=== >> "%LOG%"
dir /b D:\Git\usr\bin\bash* >> "%LOG%" 2>&1
dir /b D:\Git\usr\bin\sh* >> "%LOG%" 2>&1
echo ===COUNT=== >> "%LOG%"
dir /b D:\Git\usr\bin\*.exe 2>nul | find /c /v "" >> "%LOG%"
echo ===REG=== >> "%LOG%"
reg query HKLM\SOFTWARE\GitForWindows >> "%LOG%" 2>&1
echo ===PATH=== >> "%LOG%"
echo %PATH% >> "%LOG%"
echo ===DONE=== >> "%LOG%"
