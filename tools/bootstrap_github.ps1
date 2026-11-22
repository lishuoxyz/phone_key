# Bootstrap the GitHub repo + Pages deployment for phone_key.
#
# Usage (from the repo root):
#   powershell -ExecutionPolicy Bypass -File tools/bootstrap_github.ps1 -Token <PAT> [-Repo phone_key] [-Private]
#
# The token needs (classic PAT): repo + workflow.
# The token is only used for the API calls and the push; it is never written to
# .git/config or to disk. Keep this file ASCII-only: Windows PowerShell 5.1
# reads .ps1 as ANSI and non-ASCII text breaks parsing.

param(
    [Parameter(Mandatory = $true)][string]$Token,
    [string]$Repo = "phone_key",
    [switch]$Private
)

$ErrorActionPreference = "Stop"
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
} catch { }

$api = "https://api.github.com"
$headers = @{
    Authorization          = "Bearer $Token"
    Accept                 = "application/vnd.github+json"
    "User-Agent"           = "phone-key-bootstrap"
    "X-GitHub-Api-Version" = "2022-11-28"
}

Write-Host "== 1. verify token =="
$user = Invoke-RestMethod -Uri "$api/user" -Headers $headers
$login = $user.login
Write-Host "logged in as: $login"

Write-Host "== 2. create repository $login/$Repo =="
$body = @{
    name        = $Repo
    description = "phone key: bdb-PKE alarm control (Web Bluetooth PWA / Android)"
    private     = [bool]$Private
    has_issues  = $true
} | ConvertTo-Json
try {
    $repoInfo = Invoke-RestMethod -Method Post -Uri "$api/user/repos" -Headers $headers -Body $body
    Write-Host "created: $($repoInfo.html_url)"
} catch {
    if ($_.Exception.Response.StatusCode.value__ -eq 422) {
        Write-Host "repository already exists, reusing it"
        $repoInfo = Invoke-RestMethod -Uri "$api/repos/$login/$Repo" -Headers $headers
    } else {
        throw
    }
}

Write-Host "== 3. push main =="
# Native commands write progress/warnings to stderr; do not let that abort us.
$ErrorActionPreference = "Continue"
$cleanUrl = "https://github.com/$login/$Repo.git"
$authUrl = "https://x-access-token:$Token@github.com/$login/$Repo.git"
$existing = git remote get-url origin 2>$null
if ($LASTEXITCODE -eq 0) {
    git remote set-url origin $cleanUrl | Out-Null
} else {
    git remote add origin $cleanUrl | Out-Null
}
git push $authUrl main
if ($LASTEXITCODE -ne 0) {
    throw "git push failed (exit $LASTEXITCODE)"
}
git fetch origin 2>$null | Out-Null
git branch --set-upstream-to=origin/main main 2>$null | Out-Null
Write-Host "pushed"
$ErrorActionPreference = "Stop"

Write-Host "== 4. enable GitHub Pages (workflow build) =="
$pagesBody = @{ build_type = "workflow" } | ConvertTo-Json
try {
    Invoke-RestMethod -Method Post -Uri "$api/repos/$login/$Repo/pages" -Headers $headers -Body $pagesBody | Out-Null
    Write-Host "Pages enabled"
} catch {
    $code = $_.Exception.Response.StatusCode.value__
    if ($code -eq 409) {
        Write-Host "Pages already enabled"
        try {
            Invoke-RestMethod -Method Put -Uri "$api/repos/$login/$Repo/pages" -Headers $headers -Body $pagesBody | Out-Null
        } catch {
            Write-Host "(if Pages still builds from a branch, set Settings -> Pages -> Source = GitHub Actions)"
        }
    } else {
        Write-Host "enabling Pages returned $code; enable it manually in Settings -> Pages (Source = GitHub Actions)"
    }
}

Write-Host ""
Write-Host "== done =="
Write-Host "repo:    $cleanUrl"
Write-Host "actions: $cleanUrl/actions"
Write-Host "site:    https://$login.github.io/$Repo/"
Write-Host "the first Actions run takes about a minute; every push to main updates the site."
