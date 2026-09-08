@echo off
set LOG=D:\ServiceOps Agent\zdiag2.txt
echo ===USRBIN_EXE_BY_DATE=== > "%LOG%"
dir /o-d /t:w D:\Git\usr\bin\*.exe >> "%LOG%" 2>&1
echo ===USRBIN_DLL=== >> "%LOG%"
dir /o-d /t:w D:\Git\usr\bin\*.dll >> "%LOG%" 2>&1
echo ===GITROOT_BY_DATE=== >> "%LOG%"
dir /o-d /t:w D:\Git >> "%LOG%" 2>&1
echo ===GIT_ETC=== >> "%LOG%"
dir /o-d /t:w D:\Git\etc >> "%LOG%" 2>&1
echo ===HUORONG_TOP=== >> "%LOG%"
dir /b D:\Huorong >> "%LOG%" 2>&1
dir /b D:\Huorong\Sysdiag >> "%LOG%" 2>&1
echo ===HUORONG_LOGS=== >> "%LOG%"
dir /o-d /t:w D:\Huorong\Sysdiag\logs >> "%LOG%" 2>&1
echo ===RECYCLE=== >> "%LOG%"
dir /a /s /b D:\$Recycle.Bin >> "%LOG%" 2>&1
echo ===GITSTATUS=== >> "%LOG%"
git -C "D:\ServiceOps Agent" status --short >> "%LOG%" 2>&1
git -C "D:\ServiceOps Agent" log --oneline -5 >> "%LOG%" 2>&1
echo ===DONE=== >> "%LOG%"
