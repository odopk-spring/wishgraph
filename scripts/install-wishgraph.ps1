[CmdletBinding()]
param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet("codex", "claude-user", "claude-project")]
    [string]$Target,

    [switch]$Force,
    [switch]$SetupProject,
    [string]$Project = (Get-Location).Path,
    [switch]$Strict,
    [switch]$Check
)

$ErrorActionPreference = "Stop"

if ($PSBoundParameters.ContainsKey("Project")) {
    $SetupProject = $true
}
if ($Strict -and -not $SetupProject) {
    [Console]::Error.WriteLine("-Strict requires -SetupProject or -Project PATH.")
    exit 2
}

function Write-GitHelp {
    [Console]::Error.WriteLine("Git is required by this installer and by project memory checks.")
    [Console]::Error.WriteLine("Install: winget install --id Git.Git -e --source winget")
    [Console]::Error.WriteLine("Estimate: commonly 200-500 MB and 2-10 minutes.")
    [Console]::Error.WriteLine("Official download: https://git-scm.com/install/windows.html")
}

function Find-PythonExecutable {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        try {
            $resolved = (& py list --format=exe --one ">=3.9" 2>$null | Select-Object -First 1)
            if ($LASTEXITCODE -eq 0 -and $resolved -and (Test-Path -LiteralPath $resolved)) {
                & $resolved -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)"
                if ($LASTEXITCODE -eq 0) { return $resolved }
            }
        } catch { }
        try {
            $legacyLines = & py -0p 2>$null
            foreach ($line in $legacyLines) {
                if ($line -match "([A-Za-z]:\\.*python(?:[0-9.]*)?\.exe)\s*$") {
                    $resolved = $Matches[1]
                    & $resolved -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)"
                    if ($LASTEXITCODE -eq 0) { return $resolved }
                }
            }
        } catch { }
    }

    foreach ($name in @("python3", "python")) {
        $candidate = Get-Command $name -ErrorAction SilentlyContinue
        if (-not $candidate) { continue }
        if ($candidate.Source -like "*\WindowsApps\*") { continue }
        try {
            & $candidate.Source -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)"
            if ($LASTEXITCODE -eq 0) { return $candidate.Source }
        } catch { }
    }
    return $null
}

function Write-PythonHelp {
    [Console]::Error.WriteLine("Project hooks require Python 3.9 or newer; no third-party packages are needed.")
    [Console]::Error.WriteLine("Install manager: winget install 9NQ7512CXL7T")
    [Console]::Error.WriteLine("Then install a runtime: py install default")
    [Console]::Error.WriteLine("Estimate: commonly 100-300 MB and 2-10 minutes including one Python runtime.")
    [Console]::Error.WriteLine("Official guide: https://docs.python.org/3/using/windows.html")
}

Write-Host "WishGraph install estimate: about 0.5 MB on disk and usually under 1 minute."
if ($SetupProject) {
    Write-Host "Project hooks add about 0.3 MB and usually under 10 seconds."
}
Write-Host "Installation stage 1: checking prerequisites."

$preflightFailed = $false
$gitCommand = Get-Command git -ErrorAction SilentlyContinue
if (-not $gitCommand) {
    Write-GitHelp
    $preflightFailed = $true
}

$pythonExecutable = $null
if ($SetupProject -and -not $preflightFailed) {
    if (-not (Test-Path -LiteralPath $Project -PathType Container)) {
        [Console]::Error.WriteLine("Project directory does not exist: $Project")
        $preflightFailed = $true
    }
    if (-not $preflightFailed) {
        $pythonExecutable = Find-PythonExecutable
        if (-not $pythonExecutable) {
            Write-PythonHelp
            $preflightFailed = $true
        }
    }
    if (-not $preflightFailed) {
        $detectedRoot = (& git -C $Project rev-parse --show-toplevel 2>$null | Select-Object -First 1)
        if ($LASTEXITCODE -ne 0 -or -not $detectedRoot) {
            [Console]::Error.WriteLine("Project hooks need a Git repository, but $Project is not inside one.")
            [Console]::Error.WriteLine("Run 'git init' there, or ask your agent to initialize Git, then retry.")
            [Console]::Error.WriteLine("Estimate: under 1 MB and normally under a second.")
            $preflightFailed = $true
        } else {
            if ($detectedRoot -ne $Project) {
                Write-Host "Using detected Git repository root: $detectedRoot"
            }
            $Project = $detectedRoot
        }
    }
}

if ($preflightFailed) {
    [Console]::Error.WriteLine("Nothing was installed. Resolve the items above, reopen PowerShell if needed, and retry.")
    exit 3
}
if ($Check) {
    Write-Host "Prerequisite check passed. Nothing was installed."
    exit 0
}

$repoUrl = if ($env:WISHGRAPH_REPO_URL) { $env:WISHGRAPH_REPO_URL } else { "https://github.com/odopk-spring/wishgraph.git" }
$repoRef = if ($env:WISHGRAPH_REF) { $env:WISHGRAPH_REF } else { "main" }

switch ($Target) {
    "codex" {
        $codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
        $destination = Join-Path $codexHome "skills/wishgraph"
        $hookHost = "codex"
    }
    "claude-user" {
        $destination = Join-Path $HOME ".claude/skills/wishgraph"
        $hookHost = "claude"
    }
    "claude-project" {
        $destination = Join-Path $Project ".claude/skills/wishgraph"
        $hookHost = "claude"
    }
}

$reuseExisting = $false
if (Test-Path -LiteralPath $destination) {
    if ($Force) {
        Remove-Item -LiteralPath $destination -Recurse -Force
    } elseif ($SetupProject -and (Test-Path -LiteralPath (Join-Path $destination "scripts/install_project_hooks.py"))) {
        $reuseExisting = $true
        Write-Host "WishGraph skill already exists at $destination; reusing it for project setup."
    } else {
        [Console]::Error.WriteLine("Destination already exists: $destination. Re-run with -Force to replace it.")
        exit 1
    }
}

if (-not $reuseExisting) {
    Write-Host "Installation stage 2: installing the WishGraph Skill."
    $tempDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ("wishgraph-" + [guid]::NewGuid())
    try {
        & git clone --depth 1 --filter=blob:none --sparse --branch $repoRef $repoUrl $tempDirectory *> $null
        if ($LASTEXITCODE -ne 0) { throw "Git clone failed." }
        & git -C $tempDirectory sparse-checkout set skills/wishgraph *> $null
        if ($LASTEXITCODE -ne 0) { throw "Git sparse checkout failed." }

        New-Item -ItemType Directory -Path $destination -Force | Out-Null
        Copy-Item -Path (Join-Path $tempDirectory "skills/wishgraph/*") -Destination $destination -Recurse -Force
        Write-Host "Installed WishGraph skill to $destination"
        Write-Host "Restart your agent tool if it does not pick up new skills immediately."
    } finally {
        if (Test-Path -LiteralPath $tempDirectory) {
            Remove-Item -LiteralPath $tempDirectory -Recurse -Force
        }
    }
}

if ($Target -eq "claude-user" -or $Target -eq "claude-project") {
    $agentSource = Join-Path $destination "assets/claude-agents/wishgraph-worker.md"
    $agentDestination = if ($Target -eq "claude-user") {
        Join-Path $HOME ".claude/agents/wishgraph-worker.md"
    } else {
        Join-Path $Project ".claude/agents/wishgraph-worker.md"
    }
    if (Test-Path -LiteralPath $agentDestination) {
        $existingAgent = Get-Content -LiteralPath $agentDestination -Raw
        if (-not $existingAgent.Contains("<!-- wishgraph-managed: wishgraph-worker -->")) {
            [Console]::Error.WriteLine("Refusing to replace non-WishGraph Claude Agent: $agentDestination")
            exit 1
        }
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $agentDestination) -Force | Out-Null
    Copy-Item -LiteralPath $agentSource -Destination $agentDestination -Force
    Write-Host "Installed WishGraph Claude Worker Agent to $agentDestination"
}

if ($SetupProject) {
    Write-Host "Installation stage 3: configuring project hooks."
    $mode = if ($Strict) { "enforce" } else { "warn" }
    $installerArguments = @(
        (Join-Path $destination "scripts/install_project_hooks.py"),
        "--target", $Project,
        "--host", $hookHost,
        "--mode", $mode
    )
    if ($Strict) { $installerArguments += "--git-hook" }
    if ($Force) { $installerArguments += "--force-assets" }

    & $pythonExecutable @installerArguments
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

}
