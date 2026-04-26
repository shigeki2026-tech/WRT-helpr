@echo off
cd /d "%USERPROFILE%\Documents\Projects\WRT-helpr"
git add .
git commit -m "update"
git push
echo Done.
pause