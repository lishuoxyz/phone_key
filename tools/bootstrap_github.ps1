# Bootstrap the GitHub repo + Pages deployment for phone_key.
#
# Usage (from the repo root):
#   pwsh -File tools/bootstrap_github.ps1 -Token <PAT> [-Repo phone_key] [-Private]
#
# The token needs (classic PAT): repo + workflow.
# The token is only used for the API calls and the push; it is never written to
# .git/config or to disk.

param(
    [Parameter(Mandatory = $true)][string]$Token,
    [string]$Repo = "phone_key",
    [switch]$Private
)

$ErrorActionPreference = "Stop"
$api = "https://api.github.com"
$headers = @{
    Authorization          = "Bearer $Token"
    Accept                 = "application/vnd.github+json"
    "User-Agent"           = "phone-key-bootstrap"
    "X-GitHub-Api-Version" = "2022-11-28"
}

Write-Host "== 1. 校验 token =="
$user = Invoke-RestMethod -Uri "$api/user" -Headers $headers
$login = $user.login
Write-Host "登录为: $login"

Write-Host "== 2. 创建仓库 $login/$Repo =="
$body = @{
    name        = $Repo
    description = "手机车钥匙：bdb-PKE 报警器 Web Bluetooth / Android 控制"
    private     = [bool]$Private
    has_issues  = $true
} | ConvertTo-Json
try {
    $repoInfo = Invoke-RestMethod -Method Post -Uri "$api/user/repos" -Headers $headers -Body $body
    Write-Host "已创建: $($repoInfo.html_url)"
} catch {
    if ($_.Exception.Response.StatusCode.value__ -eq 422) {
        Write-Host "仓库已存在，继续使用"
        $repoInfo = Invoke-RestMethod -Uri "$api/repos/$login/$Repo" -Headers $headers
    } else {
        throw
    }
}

Write-Host "== 3. 推送 main =="
$cleanUrl = "https://github.com/$login/$Repo.git"
$authUrl = "https://x-access-token:$Token@github.com/$login/$Repo.git"
git remote remove origin 2>$null | Out-Null
git remote add origin $cleanUrl
git push $authUrl main
git fetch origin 2>$null | Out-Null
git branch --set-upstream-to=origin/main main 2>$null | Out-Null
Write-Host "推送完成"

Write-Host "== 4. 启用 GitHub Pages (Actions 构建) =="
$pagesBody = @{ build_type = "workflow" } | ConvertTo-Json
try {
    Invoke-RestMethod -Method Post -Uri "$api/repos/$login/$Repo/pages" -Headers $headers -Body $pagesBody | Out-Null
    Write-Host "Pages 已启用"
} catch {
    $code = $_.Exception.Response.StatusCode.value__
    if ($code -eq 409) {
        Write-Host "Pages 已经启用"
        try {
            Invoke-RestMethod -Method Put -Uri "$api/repos/$login/$Repo/pages" -Headers $headers -Body $pagesBody | Out-Null
        } catch {
            Write-Host "（如需改用 workflow 构建，请在 Settings -> Pages 里把 Source 设为 GitHub Actions）"
        }
    } else {
        Write-Host "启用 Pages 返回 $code，可在 Settings -> Pages 手动开启（Source = GitHub Actions）"
    }
}

Write-Host ""
Write-Host "== 完成 =="
Write-Host "仓库:    $cleanUrl"
Write-Host "Actions: $cleanUrl/actions"
Write-Host "页面:    https://$login.github.io/$Repo/"
Write-Host "首次 Actions 大约 1 分钟后完成，之后每次 push main 都会自动更新。"
