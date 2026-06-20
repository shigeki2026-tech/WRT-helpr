param(
    [Parameter(Position=0)]
    [ValidateSet("status", "check", "test", "run", "diff", "commit", "push", "log")]
    [string]$Action = "status",

    [Parameter(Position=1)]
    [string]$Message = ""
)

$ErrorActionPreference = "Stop"

Set-Location "$env:USERPROFILE\Documents\Projects\WRT-helpr"

function Show-Header($text) {
    Write-Host ""
    Write-Host "==== $text ===="
}

switch ($Action) {
    "status" {
        Show-Header "Git status"
        git status --short

        Show-Header "Recent commits"
        git --no-pager log --oneline -5
    }

    "check" {
        Show-Header "Python compile"
        python -m py_compile .\app.py

        Show-Header "Diff stat"
        git --no-pager diff --stat

        Show-Header "Diff check"
        git --no-pager diff --check

        Show-Header "Git status"
        git status --short
    }

    "test" {
        Show-Header "Python compile"
        python -m py_compile .\app.py

        Show-Header "Pytest"
        python -m pytest -q

        Show-Header "Diff check"
        git --no-pager diff --check

        Show-Header "Git status"
        git status --short
    }

    "run" {
        Show-Header "Run Streamlit"
        streamlit run app.py
    }

    "diff" {
        Show-Header "Diff stat"
        git --no-pager diff --stat

        Show-Header "Diff"
        git --no-pager diff
    }

    "commit" {
        if ([string]::IsNullOrWhiteSpace($Message)) {
            throw "commit にはメッセージが必要です。例: .\tools\wrt.ps1 commit ""Fix call line sync"""
        }

        Show-Header "Pre-commit check"
        python -m py_compile .\app.py
        git --no-pager diff --check
        git status --short

        Show-Header "Commit app.py only"
        git add .\app.py
        git commit -m $Message

        Show-Header "Post-commit status"
        git status --short
        git --no-pager log --oneline -3
    }

    "push" {
        Show-Header "Git status before push"
        git status --short

        Show-Header "Push"
        git push origin main

        Show-Header "Recent commits"
        git --no-pager log --oneline -3
    }

    "log" {
        git --no-pager log --oneline -10
    }
}
