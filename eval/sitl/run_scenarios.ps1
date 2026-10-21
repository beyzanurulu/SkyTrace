# Run the whole SITL campaign from Windows and keep the PC awake while it flies.
#
#   powershell -ExecutionPolicy Bypass -File eval\sitl\run_scenarios.ps1
#
# 1. writes data\sitl\plan.tsv if it does not exist (eval/sitl_plan.py defaults)
# 2. flies it inside Ubuntu (eval/sitl/run_scenarios.sh); already recorded runs are skipped
# 3. writes labels (eval/label_sitl.py) and runs the evaluation (eval/run_eval.py)
param(
    [string]$Distro = "Ubuntu-22.04"
)
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo
$env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + $env:Path

# Prevent sleep (not the display) until this script exits: a suspended PC
# desynchronises PX4 and Gazebo and ruins the running flight.
Add-Type -Namespace SkyTrace -Name Power -MemberDefinition @"
[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint flags);
"@
$ES_CONTINUOUS = [uint32]"0x80000000"; $ES_SYSTEM_REQUIRED = [uint32]"0x00000001"
[void][SkyTrace.Power]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED)

try {
    if (-not (Test-Path "data\sitl\plan.tsv")) { uv run python eval/sitl_plan.py }
    # Forward slashes: backslashes do not survive the hand-off to wsl.exe.
    $script = (wsl -d $Distro -- wslpath -a (($repo + "\eval\sitl\run_scenarios.sh") -replace "\\", "/")).Trim()
    wsl -d $Distro -- bash $script
    uv run python eval/label_sitl.py
    uv run python eval/run_eval.py
}
finally {
    [void][SkyTrace.Power]::SetThreadExecutionState($ES_CONTINUOUS)
}
