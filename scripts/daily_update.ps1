# =====================================================================
# 每日資料更新（本機排程用）
# =====================================================================
# 由 Windows 工作排程器每天執行一次，把全部資料更新到最新交易日並推送。
#
# 為什麼需要這支腳本：
#   本 repo 的 GitHub Actions 排程從未被觸發過（schedule 事件總數為 0，
#   執行紀錄全部來自手動 workflow_dispatch）。檔案格式、workflow 註冊狀態、
#   repo 設定、GitHub 服務狀態都已排除，判斷是 GitHub 端的問題。
#   因此改由本機排程負責，GitHub Actions 退居備援。
#
# 電腦不需要整天開著：
#   工作排程器勾選「錯過排定時間後盡快啟動」，關機期間錯過的執行會在下次開機後補跑。
#   收盤價是固定的，晚幾小時抓結果完全一樣。
#
# 手動執行：
#   powershell -ExecutionPolicy Bypass -File scripts\daily_update.ps1
# =====================================================================

$ErrorActionPreference = 'Continue'

# PowerShell 預設用主控台的 ANSI 編碼(cp950)讀取子程序輸出，
# 但 Python 以 UTF-8 輸出中文，不設這兩行日誌裡的中文會全部變亂碼。
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$Repo = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Repo 'logs'
$LogFile = Join-Path $LogDir ("daily_update_{0}.log" -f (Get-Date -Format 'yyyy-MM'))

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

function Write-Log {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Write-Output $line
    Add-Content -Path $LogFile -Value $line -Encoding utf8
}

# Python 可能不在工作排程器的 PATH 裡，逐一嘗試常見位置
function Resolve-Python {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $cmd) { return $cmd.Source }
    foreach ($p in @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:ProgramFiles\Python312\python.exe",
        "$env:ProgramFiles\Python311\python.exe"
    )) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

Set-Location $Repo
Write-Log "===== 開始每日更新（$Repo）====="

$Python = Resolve-Python
if ($null -eq $Python) {
    Write-Log "找不到 python，中止。請確認 Python 已安裝並在 PATH 中。"
    exit 1
}
Write-Log "使用 Python：$Python"

# 讓 Python 的中文輸出不會因為主控台編碼而壞掉
$env:PYTHONIOENCODING = 'utf-8'

# 執行順序有相依性：
#   build_index_compare.py 以 quanta_latest.json 的日線日期當交易日曆，
#   必須排在 update_stock.py 之後，否則會判定「沒有新交易日要抓」而永遠停在舊日期。
$Steps = @(
    @{ Name = '收盤報價（證交所 MIS）'; Script = 'scripts\fetch_realtime_quotes.py' },
    @{ Name = '廣達日線（提供交易日曆）'; Script = 'scripts\update_stock.py' },
    @{ Name = '16 檔類股資料';           Script = 'scripts\build_sector_data.py' },
    @{ Name = '類股指數對照';             Script = 'scripts\build_index_compare.py' },
    @{ Name = '三大法人買賣超';           Script = 'scripts\build_institutional_data.py' },
    @{ Name = '類股新聞';                 Script = 'scripts\build_news.py' },
    # 訊號必須排最後：build_signals.py 不連網，它是把上面五份 JSON 換算成
    # 評分與進出場價位，任何一份沒更新到，算出來的訊號就是舊的。
    @{ Name = '投資策略訊號';             Script = 'scripts\build_signals.py' },
    # 龍頭個股專頁的長期日線：同樣不連網，從既有 JSON 增量累積
    @{ Name = '龍頭個股日線';             Script = 'scripts\build_leader_history.py' }
)

$Failed = @()
foreach ($step in $Steps) {
    Write-Log "--- $($step.Name) ---"
    & $Python $step.Script 2>&1 | ForEach-Object { Write-Log "    $_" }
    if ($LASTEXITCODE -ne 0) {
        Write-Log "    [警告] $($step.Name) 結束碼 $LASTEXITCODE，繼續執行後續步驟"
        $Failed += $step.Name
    }
}

# ---------------------------------------------------------------- 提交推送
$DataFiles = @(
    'data/realtime.json',
    'data/quanta_latest.json',
    'data/sector_stocks.json',
    'data/index_compare.json',
    'data/institutional.json',
    'data/news.json',
    'data/signals.json',
    'data/leaders_history.json'
)

git diff --quiet -- $DataFiles
if ($LASTEXITCODE -eq 0) {
    Write-Log "資料無變動（可能非交易日或尚未收盤），略過提交"
} else {
    Write-Log "--- 提交並推送 ---"
    git add $DataFiles
    $msg = "chore: 每日資料更新 ({0})" -f (Get-Date -Format 'yyyy-MM-dd')
    git commit -q -m $msg
    git push origin main 2>&1 | ForEach-Object { Write-Log "    $_" }
    if ($LASTEXITCODE -eq 0) {
        Write-Log "推送成功"
    } else {
        Write-Log "[警告] 推送失敗（結束碼 $LASTEXITCODE）。提交已保留在本地，下次執行會一併推送。"
    }
}

if ($Failed.Count -gt 0) {
    Write-Log "本次有 $($Failed.Count) 個步驟失敗：$($Failed -join '、')"
} else {
    Write-Log "全部步驟完成"
}
Write-Log "===== 結束 ====="
