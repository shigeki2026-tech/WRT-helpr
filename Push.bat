@echo off
cd /d "%USERPROFILE%\Documents\Projects\WRT-helpr"

git status --short

git add app.py
git add data
git add tests
git add scripts
git add docs
git add config/teams_config.example.json
git add .gitignore
git add pytest.ini
git add Push.bat

git diff --cached --quiet
if %ERRORLEVEL%==0 (
    echo No staged changes.
    pause
    exit /b 0
)

git diff --cached --stat

git commit -m "update"
git push origin main

echo Done.
pause