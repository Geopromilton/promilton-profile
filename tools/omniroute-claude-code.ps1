<#
.SYNOPSIS
  Configure the Claude Code CLI (native Windows PowerShell) to route through OmniRoute.

.DESCRIPTION
  Scope: the terminal Claude Code CLI only. The Claude Desktop app cannot be routed
  through OmniRoute. It signs in with a Claude subscription over OAuth, and an OAuth
  token is only valid against Anthropic's own endpoint, so the app sets
  ANTHROPIC_BASE_URL from its internal API host and blanks ANTHROPIC_API_KEY /
  ANTHROPIC_AUTH_TOKEN / ANTHROPIC_CUSTOM_HEADERS on the agent child process. This
  script has no desktop mode and will not pretend otherwise.

.EXAMPLE
  .\omniroute-claude-code.ps1 check
  .\omniroute-claude-code.ps1 models free
  .\omniroute-claude-code.ps1 setup
  .\omniroute-claude-code.ps1 setup auto/best-coding
  .\omniroute-claude-code.ps1 verify
  .\omniroute-claude-code.ps1 revert
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('check', 'models', 'setup', 'verify', 'revert', 'help')]
    [string]$Command = 'help',

    [Parameter(Position = 1)]
    [string]$Model,

    [string]$Url = 'http://localhost:20128',
    [string]$Key = 'omniroute',
    [string]$ProfilePath,
    [switch]$Force,
    [switch]$Yes
)

# Default routes to free models only, so this works without a paid provider key.
$DefaultModel = 'auto/best-free'

$BeginMark = '# === OmniRoute Configuration for Claude Code CLI ==='
$EndMark   = '# === End OmniRoute Configuration ==='

# Pinned in settings.json's env block, these beat the shell environment.
$ConflictKeys = @(
    'ANTHROPIC_MODEL'
    'ANTHROPIC_DEFAULT_OPUS_MODEL'
    'ANTHROPIC_DEFAULT_SONNET_MODEL'
    'ANTHROPIC_DEFAULT_HAIKU_MODEL'
    'ANTHROPIC_SMALL_FAST_MODEL'
)

$EnvVarNames = @(
    'ANTHROPIC_BASE_URL'
    'ANTHROPIC_API_KEY'
    'ANTHROPIC_MODEL'
    'CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY'
    'CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT'
)

function Write-Ok   { param($m) Write-Host "  $m" -ForegroundColor Green }
function Write-Warn { param($m) Write-Host "  $m" -ForegroundColor Yellow }
function Write-Err  { param($m) Write-Host "  $m" -ForegroundColor Red }
function Write-Step { param($m) Write-Host $m -ForegroundColor White }

# The gateway base URL must not carry a /v1 suffix; Claude Code appends the path itself.
$Url = $Url.TrimEnd('/')
if ($Url -match '/v1$') {
    Write-Err "ANTHROPIC_BASE_URL must not include a /v1 suffix. Use $($Url -replace '/v1$','')"
    exit 1
}

# ---------------------------------------------------------------- profile discovery

# Windows PowerShell 5.1 and PowerShell 7 read DIFFERENT profile files. Setting the
# block in one and running claude from the other is a silent no-op. Documents may also
# be redirected to OneDrive, so resolve it properly rather than assuming $HOME\Documents.
function Get-ProfileCandidates {
    $docs = [Environment]::GetFolderPath('MyDocuments')
    [pscustomobject]@{
        PS5 = Join-Path $docs 'WindowsPowerShell\Microsoft.PowerShell_profile.ps1'
        PS7 = Join-Path $docs 'PowerShell\Microsoft.PowerShell_profile.ps1'
    }
}

function Resolve-TargetProfile {
    if ($ProfilePath) { return $ProfilePath }
    return $PROFILE.CurrentUserCurrentHost
}

# ---------------------------------------------------------------- execution policy

# If the policy is Restricted or AllSigned, the profile never runs at all, so the env
# block is written and silently ignored. This is the Windows analogue of the
# settings.json override trap: config that looks applied but is not.
function Test-ProfileWillLoad {
    Write-Step 'Checking execution policy (profiles do not load under Restricted)'
    $ep = Get-ExecutionPolicy -Scope CurrentUser
    $effective = Get-ExecutionPolicy
    if ($effective -in @('Restricted', 'AllSigned')) {
        Write-Err "effective execution policy is '$effective' - your PowerShell profile will NOT load."
        Write-Host '  Any env block written here would be silently ignored. Fix with:'
        Write-Host '    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned'
        return $false
    }
    Write-Ok "execution policy '$effective' allows profiles to load (CurrentUser: $ep)."
    return $true
}

# ---------------------------------------------------------------- step 1: gateway preflight

function Test-Gateway {
    Write-Step "Step 1 - proving the gateway is up at $Url"
    $body = @{
        model      = $DefaultModel
        max_tokens = 50
        messages   = @(@{ role = 'user'; content = 'Reply with exactly: OMNIROUTE_OK' })
    } | ConvertTo-Json -Depth 5

    try {
        $resp = Invoke-RestMethod -Uri "$Url/v1/messages" -Method Post -TimeoutSec 30 `
            -Headers @{ 'x-api-key' = $Key; 'anthropic-version' = '2023-06-01' } `
            -ContentType 'application/json' -Body $body
        $text = ($resp.content | ForEach-Object { $_.text }) -join ' '
        if ($text -match 'OMNIROUTE_OK') {
            Write-Ok 'gateway answered in Anthropic Messages format. OK.'
            return $true
        }
        Write-Warn "gateway responded, but not with the expected text:"
        Write-Host "    $($text.Substring(0, [Math]::Min(300, $text.Length)))"
        return $true
    }
    catch {
        $detail = ''
        if ($_.ErrorDetails -and $_.ErrorDetails.Message) { $detail = $_.ErrorDetails.Message }
        elseif ($_.Exception.Message) { $detail = $_.Exception.Message }

        # A model/provider complaint still proves the gateway is listening and speaking
        # its own error dialect - routing works, the probe model is just wrong.
        if ($detail -match 'provider|ambiguous|model') {
            Write-Warn "gateway is up, but rejected the probe model '$DefaultModel':"
            Write-Host "    $($detail.Substring(0, [Math]::Min(300, $detail.Length)))"
            Write-Warn 'That error came FROM OmniRoute, so routing works. Pick a model it serves.'
            return $true
        }
        Write-Err "could not reach $Url"
        Write-Host "    $($detail.Substring(0, [Math]::Min(300, $detail.Length)))"
        Write-Host '  Start it with:  omniroute        # keep it running in its own terminal'
        return $false
    }
}

# ---------------------------------------------------------------- model listing

function Get-GatewayModels {
    try {
        $resp = Invoke-RestMethod -Uri "$Url/v1/models" -Method Get -TimeoutSec 30 `
            -Headers @{ 'x-api-key' = $Key }
        return @($resp.data | ForEach-Object { $_.id })
    }
    catch { return @() }
}

function Invoke-ModelList {
    $all = Get-GatewayModels
    if ($all.Count -eq 0) {
        Write-Err "could not list models from $Url/v1/models - is OmniRoute running?"
        exit 1
    }
    if ($Model) {
        $hits = @($all | Where-Object { $_ -like "*$Model*" })
        if ($hits.Count -eq 0) { Write-Host "(no id matching '$Model')" } else { $hits }
    }
    else { $all }
}

# A bare provider name is not a model id and fails with
# "Unable to determine provider for model '<name>'".
$KnownProviders = @('openrouter','kimi','groq','anthropic','openai','gh','aug',
                    'together','fireworks','deepseek','mistral','ollama')

function Test-ModelId {
    param([string]$m)

    if ($KnownProviders -contains $m.ToLower()) {
        Write-Err "'$m' is a provider, not a model id - it will fail with:"
        Write-Host "    Unable to determine provider for model '$m'"
        Write-Host ''
        Write-Host '  Model ids that provider exposes in your install:'
        Get-GatewayModels | Where-Object { $_ -like "$m/*" } |
            Select-Object -First 40 | ForEach-Object { Write-Host "    $_" }
        Write-Host ''
        Write-Host '  Re-run with one of those ids, or an auto/* combo such as auto/best-free.'
        exit 1
    }

    $all = Get-GatewayModels
    if ($all.Count -eq 0) {
        Write-Warn 'could not read /v1/models; skipping id validation.'
        return
    }
    if ($all -contains $m) {
        Write-Ok "'$m' exists in this install."
        return
    }

    # Custom dashboard combos resolve on their own and need not appear in /v1/models.
    if ($m -match '/') {
        Write-Err "'$m' is not listed by /v1/models in this install."
        $leaf = ($m -split '/')[-1]
        Write-Host '  Close matches:'
        $all | Where-Object { $_ -like "*$leaf*" } | Select-Object -First 10 |
            ForEach-Object { Write-Host "    $_" }
        if (-not $Force) {
            Write-Host ''
            Write-Host '  Re-run with -Force only if you are sure.'
            exit 1
        }
        Write-Warn '-Force given; writing it anyway.'
    }
    else {
        Write-Warn "'$m' is not in /v1/models. Bare names are treated as dashboard combos,"
        Write-Warn 'which resolve on their own and are often not listed - continuing.'
        Write-Warn 'If it is not a combo you created, this will fail at request time.'
    }
}

# ---------------------------------------------------------------- step 3: settings.json

function Test-ClaudeSettings {
    Write-Step 'Step 3 - checking settings.json for an env block that overrides the shell'
    $found = $false
    $paths = @(
        (Join-Path $env:USERPROFILE '.claude\settings.json')
        (Join-Path $env:USERPROFILE '.claude\settings.local.json')
        (Join-Path (Get-Location) '.claude\settings.json')
        (Join-Path (Get-Location) '.claude\settings.local.json')
    )

    foreach ($p in $paths) {
        if (-not (Test-Path $p)) { continue }
        try { $d = Get-Content $p -Raw | ConvertFrom-Json }
        catch {
            Write-Host "  in ${p}:"
            Write-Err "  not valid JSON: $($_.Exception.Message)"
            $found = $true
            continue
        }

        $lines = @()
        $envProp = $d.PSObject.Properties['env']
        if ($envProp -and $envProp.Value) {
            $e = $envProp.Value
            foreach ($k in $ConflictKeys) {
                if ($e.PSObject.Properties[$k]) {
                    $lines += @{ Kind = 'err'; Text = "$k=$($e.$k) - overrides your shell; remove it or set a valid OmniRoute id" }
                }
            }
            if ($e.PSObject.Properties['ANTHROPIC_BASE_URL']) {
                $lines += @{ Kind = 'warn'; Text = "env.ANTHROPIC_BASE_URL=$($e.ANTHROPIC_BASE_URL) - only honored if nothing else set it" }
            }
            if ($e.PSObject.Properties['ANTHROPIC_API_KEY']) {
                $lines += @{ Kind = 'warn'; Text = 'env.ANTHROPIC_API_KEY present - never honored as a credential' }
            }
        }
        if ($d.PSObject.Properties['model']) {
            $lines += @{ Kind = 'err'; Text = "top-level `"model`": $($d.model) - resolves via ANTHROPIC_DEFAULT_*; remove it" }
        }

        if ($lines.Count -gt 0) {
            Write-Host "  in ${p}:"
            foreach ($l in $lines) {
                if ($l.Kind -eq 'err') { Write-Err "  $($l.Text)"; $found = $true }
                else { Write-Warn "  $($l.Text)" }
            }
        }
    }

    if ($found) {
        Write-Host ''
        Write-Warn 'Precedence, highest wins:  --model flag  >  settings.json env  >  shell environment'
        Write-Warn 'Fix those by hand before trusting the profile block. Not edited automatically -'
        Write-Warn 'settings.json is yours and may hold unrelated configuration.'
        return $false
    }
    Write-Ok 'no conflicting model pins found.'
    return $true
}

# ---------------------------------------------------------------- profile block writing

function Remove-Block {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $false }
    $lines = @(Get-Content $Path)
    if ($lines -notcontains $BeginMark) { return $false }

    $backup = "$Path.omniroute.bak.$(Get-Date -Format 'yyyyMMddHHmmss')"
    Copy-Item $Path $backup -Force

    $out = @(); $skip = $false
    foreach ($ln in $lines) {
        if ($ln.Trim() -eq $BeginMark) { $skip = $true; continue }
        if ($ln.Trim() -eq $EndMark)   { $skip = $false; continue }
        if (-not $skip) { $out += $ln }
    }
    Set-Content -Path $Path -Value $out -Encoding UTF8
    Write-Ok "removed existing block from $Path (backup: $backup)"
    return $true
}

function Write-Block {
    param([string]$Path, [string]$m)
    Write-Step "Step 2 - writing the env block to $Path"

    $dir = Split-Path $Path -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    if (-not (Test-Path $Path)) { New-Item -ItemType File -Path $Path -Force | Out-Null }

    Remove-Block -Path $Path | Out-Null

    $block = @(
        ''
        $BeginMark
        "`$env:ANTHROPIC_BASE_URL = '$Url'"
        "`$env:ANTHROPIC_API_KEY = '$Key'"
        "`$env:ANTHROPIC_MODEL = '$m'"
        "`$env:CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY = '1'"
        "`$env:CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT = '1'"
        $EndMark
    )
    Add-Content -Path $Path -Value $block -Encoding UTF8
    Write-Ok 'block written.'

    # Apply to the current session too, so verify works without reopening the terminal.
    $env:ANTHROPIC_BASE_URL = $Url
    $env:ANTHROPIC_API_KEY = $Key
    $env:ANTHROPIC_MODEL = $m
    $env:CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY = '1'
    $env:CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT = '1'
    Write-Ok 'also applied to this session.'
}

# ---------------------------------------------------------------- step 4: verify

function Invoke-Verify {
    $m = if ($Model) { $Model } elseif ($env:ANTHROPIC_MODEL) { $env:ANTHROPIC_MODEL } else { $DefaultModel }
    Write-Step 'Step 4 - verifying the request actually reaches the gateway'

    if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
        Write-Warn 'claude CLI not on PATH; skipping.'
        return $true
    }

    $out = (& claude -p 'Reply with exactly: OMNIROUTE_OK' --model $m --max-turns 1 2>&1) -join "`n"

    if ($out -match 'OMNIROUTE_OK') {
        Write-Ok 'working - Claude Code is routing through OmniRoute.'
        return $true
    }
    if ($out -match 'provider|ambiguous') {
        Write-Warn 'routing works (this error came from OmniRoute), but the model id is wrong:'
        Write-Host "    $($out.Substring(0, [Math]::Min(300, $out.Length)))"
        Write-Host '  Fix ANTHROPIC_MODEL, and re-check settings.json (step 3).'
        return $false
    }
    if ($out -match 'Invalid API key') {
        Write-Err 'still hitting Anthropic directly - the env block did not apply.'
        Write-Host '  Did you open a new terminal? Is the profile the one your shell actually loads?'
        Write-Host '  A settings.json env block may also be overriding it (step 3).'
        return $false
    }
    Write-Warn 'unrecognized result:'
    Write-Host "    $($out.Substring(0, [Math]::Min(300, $out.Length)))"
    return $false
}

# ---------------------------------------------------------------- commands

function Invoke-Check {
    $gw = Test-Gateway
    Write-Host ''
    $pol = Test-ProfileWillLoad
    Write-Host ''
    $cand = Get-ProfileCandidates
    Write-Step 'PowerShell profile locations (5.1 and 7 are different files)'
    Write-Host "    running:            $($PSVersionTable.PSVersion) -> $($PROFILE.CurrentUserCurrentHost)"
    Write-Host "    Windows PowerShell: $($cand.PS5)$(if (Test-Path $cand.PS5) { ' [exists]' })"
    Write-Host "    PowerShell 7:       $($cand.PS7)$(if (Test-Path $cand.PS7) { ' [exists]' })"
    foreach ($p in @($cand.PS5, $cand.PS7)) {
        if ((Test-Path $p) -and (@(Get-Content $p) -contains $BeginMark)) {
            Write-Ok "OmniRoute block present in $p"
        }
    }
    Write-Host ''
    $st = Test-ClaudeSettings
    if ($gw -and $pol -and $st) { exit 0 } else { exit 1 }
}

function Invoke-Setup {
    $m = if ($Model) { $Model } else { $DefaultModel }
    if (-not $Model) { Write-Warn "No model given; defaulting to $DefaultModel." }

    if (-not (Test-Gateway)) {
        Write-Err 'gateway is not usable - fix OmniRoute before changing any config.'
        exit 1
    }
    Write-Host ''
    if (-not (Test-ProfileWillLoad)) {
        Write-Err 'refusing to write a profile block that cannot load.'
        exit 1
    }
    Write-Host ''
    Write-Step "Validating '$m'"
    Test-ModelId -m $m
    Write-Host ''
    $settingsOk = Test-ClaudeSettings
    Write-Host ''

    $target = Resolve-TargetProfile
    if (-not $Yes) {
        $reply = Read-Host "Write ANTHROPIC_MODEL=$m to $target ? [y/N]"
        if ($reply -notmatch '^(y|Y|yes|YES)$') { Write-Host 'aborted.'; exit 1 }
    }
    Write-Block -Path $target -m $m
    Write-Host ''

    $cand = Get-ProfileCandidates
    $other = if ($target -eq $cand.PS7) { $cand.PS5 } elseif ($target -eq $cand.PS5) { $cand.PS7 } else { $null }
    if ($other) {
        Write-Warn "Written for THIS PowerShell only. If you also run claude from the other"
        Write-Warn "PowerShell edition, repeat with:  -ProfilePath '$other'"
    }
    if (-not $settingsOk) { Write-Warn 'Resolve the settings.json conflicts above first.' }
    Write-Host ''
    Write-Host '  Then run:  .\omniroute-claude-code.ps1 verify'
}

function Invoke-Revert {
    Write-Step 'Reverting to stock Claude'
    $cand = Get-ProfileCandidates
    $any = $false
    foreach ($p in @($cand.PS5, $cand.PS7, $PROFILE.CurrentUserCurrentHost)) {
        if (Remove-Block -Path $p) { $any = $true }
    }
    if (-not $any) { Write-Host '  no OmniRoute block found in any profile' }

    # Clear persistent user-level variables a previous guide may have set via setx.
    foreach ($v in $EnvVarNames) {
        if ([Environment]::GetEnvironmentVariable($v, 'User')) {
            [Environment]::SetEnvironmentVariable($v, $null, 'User')
            Write-Ok "cleared user-level $v"
        }
        Remove-Item "env:$v" -ErrorAction SilentlyContinue
    }
    Write-Host '  Open a new terminal for this to take effect.'
}

switch ($Command) {
    'check'  { Invoke-Check }
    'models' { Invoke-ModelList }
    'setup'  { Invoke-Setup }
    'verify' { if (Invoke-Verify) { exit 0 } else { exit 1 } }
    'revert' { Invoke-Revert }
    default  { Get-Help $MyInvocation.MyCommand.Path -Detailed }
}
