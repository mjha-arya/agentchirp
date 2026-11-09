# Registers the Windows Scheduled Task "AgentChirp": every day at 10:50, run the pipeline so the
# voice note lands at 11:00.
#
# Nothing here runs until you run it. Open PowerShell in this folder and:
#
#     .\schedule.ps1            # register (or update) the task
#     .\schedule.ps1 -WhatIf    # show what it would do and change nothing
#     .\schedule.ps1 -Remove    # unregister the task again
#
# No admin rights needed: the task is registered for your own account and runs only when you are
# logged on. Check it afterwards with:  Get-ScheduledTask AgentChirp | Get-ScheduledTaskInfo

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$TaskName = 'AgentChirp',
    [string]$At = '10:50',
    [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

if ($Remove) {
    if ($PSCmdlet.ShouldProcess($TaskName, 'Unregister scheduled task')) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed scheduled task '$TaskName'."
    }
    return
}

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { throw 'python is not on PATH. AgentChirp needs system Python 3.12 (no venv).' }

# Resolve the launcher shim to the real interpreter so the task does not depend on PATH.
$python = (& $python -c "import sys; print(sys.executable)").Trim()

$action = New-ScheduledTaskAction -Execute $python -Argument '-m agentchirp run' -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

if ($PSCmdlet.ShouldProcess("$TaskName at $At daily", "Register scheduled task running `"$python -m agentchirp run`" in $root")) {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal -Force `
        -Description 'AgentChirp: morning X trend brief, sent to Telegram as a voice note.' | Out-Null
    Write-Host "Registered '$TaskName' - daily at $At, running: $python -m agentchirp run"
    Write-Host "Working directory: $root"
    Write-Host 'Sign in to X first:  python -m agentchirp login'
}
