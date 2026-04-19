[CmdletBinding()]
param(
    [ValidateSet('start','stop','status','wallet','address','repair-peers')]
    [string]$Command = 'start'
)

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir '..\..')).Path
$BinDir = if ($env:QBTC_BINDIR) { $env:QBTC_BINDIR } else { Join-Path $RepoRoot 'src' }
$DataDir = if ($env:QBTC_DATADIR) { $env:QBTC_DATADIR } else { Join-Path $env:LOCALAPPDATA 'Bitcoin' }
$ConfPath = if ($env:QBTC_CONF) { $env:QBTC_CONF } else { Join-Path $DataDir 'bitcoin.conf' }
$TemplateConf = Join-Path $ScriptDir 'qbtc-windows-low-spec.conf'
$Bitcoind = Join-Path $BinDir 'bitcoind.exe'
$Cli = Join-Path $BinDir 'bitcoin-cli.exe'
$Wallet = if ($env:QBTC_WALLET) { $env:QBTC_WALLET } else { 'miner' }
$ChainArgs = @('-chain=qbtctestnet', "-conf=$ConfPath")
$BootstrapPeers = @(
    '46.62.156.169:28333',
    '37.27.47.236:28333',
    '89.167.109.241:28333'
)

function Ensure-DataDir {
    if (-not (Test-Path $DataDir)) {
        New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
    }
}

function Ensure-Config {
    Ensure-DataDir
    if (-not (Test-Path $ConfPath)) {
        Copy-Item $TemplateConf $ConfPath -Force
        Write-Host "Created default config at $ConfPath"
        return
    }

    if (-not (Select-String -Path $ConfPath -SimpleMatch '[qbtctestnet]' -Quiet)) {
        Add-Content -Path $ConfPath -Value @"

[qbtctestnet]
server=1
listen=1
discover=1
dnsseed=1
fallbackfee=0.0001
prune=5500
dbcache=128
maxmempool=150
maxconnections=16
maxsigcachesize=16
seednode=46.62.156.169:28333
seednode=37.27.47.236:28333
seednode=89.167.109.241:28333
addnode=46.62.156.169:28333
addnode=37.27.47.236:28333
addnode=89.167.109.241:28333
"@
        Write-Host "Added qbtctestnet defaults to $ConfPath"
    }
}

function Invoke-CLI {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    & $Cli @ChainArgs @Args
}

function Wait-Rpc {
    param([int]$Tries = 60)
    for ($i = 0; $i -lt $Tries; $i++) {
        try {
            $null = Invoke-CLI 'getblockchaininfo'
            return $true
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    return $false
}

function Ensure-Binaries {
    if (-not (Test-Path $Bitcoind)) { throw "bitcoind.exe not found at $Bitcoind" }
    if (-not (Test-Path $Cli)) { throw "bitcoin-cli.exe not found at $Cli" }
}

function Repair-Peers {
    try {
        $count = [int](Invoke-CLI 'getconnectioncount')
    } catch {
        $count = 0
    }

    if ($count -ge 2) {
        Write-Host "Peer count healthy: $count"
        return
    }

    foreach ($peer in $BootstrapPeers) {
        try {
            Invoke-CLI 'addnode' $peer 'add' | Out-Null
        } catch {
            try { Invoke-CLI 'addnode' $peer 'onetry' | Out-Null } catch {}
        }
    }

    Start-Sleep -Seconds 3
    try {
        $count = [int](Invoke-CLI 'getconnectioncount')
        Write-Host "Peer count after bootstrap: $count"
    } catch {
        Write-Host 'Peer repair attempted.'
    }
}

function Ensure-Wallet {
    try {
        Invoke-CLI "-rpcwallet=$Wallet" 'getwalletinfo' | Out-Null
        return
    } catch {}

    try {
        Invoke-CLI 'loadwallet' $Wallet | Out-Null
    } catch {
        Invoke-CLI 'createwallet' $Wallet | Out-Null
    }
}

function Show-Status {
    $info = Invoke-CLI 'getblockchaininfo' | ConvertFrom-Json
    $peers = [int](Invoke-CLI 'getconnectioncount')
    Write-Host 'QuantumBTC Node Status'
    Write-Host '======================='
    Write-Host ("Chain:      {0}" -f $info.chain)
    Write-Host ("Blocks:     {0}" -f $info.blocks)
    Write-Host ("Headers:    {0}" -f $info.headers)
    Write-Host ("Peers:      {0}" -f $peers)
    Write-Host ("Difficulty: {0}" -f $info.difficulty)
    Write-Host ("IBD:        {0}" -f $info.initialblockdownload)
    Write-Host ("PQC:        {0}" -f $info.pqc)
    Write-Host ("DAG mode:   {0}" -f $info.dagmode)
}

function Start-Node {
    Ensure-Binaries
    Ensure-Config

    if (Wait-Rpc -Tries 2) {
        Write-Host 'QuantumBTC node is already running.'
        Show-Status
        return
    }

    $args = @(
        '-chain=qbtctestnet',
        "-conf=$ConfPath",
        '-server=1',
        '-listen=1',
        '-discover=1',
        '-dnsseed=1',
        '-fallbackfee=0.0001',
        '-prune=5500',
        '-dbcache=128',
        '-maxmempool=150',
        '-maxconnections=16',
        '-maxsigcachesize=16',
        '-logtimestamps=1',
        '-txindex=0'
    )

    Start-Process -FilePath $Bitcoind -ArgumentList $args -WindowStyle Hidden | Out-Null

    if (-not (Wait-Rpc)) {
        throw 'Node started process but RPC never became ready.'
    }

    Repair-Peers
    Show-Status
}

function Stop-Node {
    Ensure-Config
    Invoke-CLI 'stop'
    Write-Host 'Shutdown signal sent.'
}

function Show-Address {
    Ensure-Wallet
    $addr = Invoke-CLI "-rpcwallet=$Wallet" 'getnewaddress' '' 'bech32'
    Write-Host $addr
}

switch ($Command) {
    'start'        { Start-Node }
    'stop'         { Stop-Node }
    'status'       { Ensure-Config; Ensure-Binaries; Show-Status }
    'wallet'       { Ensure-Config; Ensure-Binaries; Ensure-Wallet; Write-Host "Wallet ready: $Wallet" }
    'address'      { Ensure-Config; Ensure-Binaries; Show-Address }
    'repair-peers' { Ensure-Config; Ensure-Binaries; Repair-Peers; Show-Status }
}
