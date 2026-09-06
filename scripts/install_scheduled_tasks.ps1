<#
.SYNOPSIS
Install or remove the two user-level scheduled tasks that run the observatory's
unattended publish loop (Plan B Task B2).

.DESCRIPTION
Registers, without elevation:

  "Observatory SE sweep"  - daily 07:30 and 19:30 local: make auto SOURCES=jobtech
  "Observatory BA sweep"  - daily 13:00 local:            make auto SOURCES=ba

The BA slot is 13:00 by owner decision (2026-09-05): the PC is off overnight, so the
plan's original 02:00 slot would never fire; 13:00 keeps the daily BA cadence (and the
24 h freshness threshold) honest in PC-on hours. Missed slots (PC off) self-heal via
start-when-available at the next logon, and the orchestrator's spacing guard prevents
a catch-up over-sweep.

Both tasks run B1's orchestrator (scripts/auto_sweep.py via the Makefile `auto`
target) with the repository as working directory. The orchestrator enforces its
own laws: spacing guard (jobtech >= 2 h, ba >= 20 h), gates in the runbook's
order, and it never commits a red gate - any failing step exits 1 before the
commit and leaves the evidence in logs/auto/<run id>.log.

Tasks are registered DISABLED by default so nothing fires before an explicit
enable decision. -Enable registers them enabled instead. -Remove unregisters
both (the reverse of the install).

Status of the underlying data (partition ages, spacing verdicts, freshness):
  uv run --offline python scripts/auto_sweep.py --status

.PARAMETER Remove
Unregister both tasks instead of registering them.

.PARAMETER Enable
Register the tasks enabled rather than disabled.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File scripts\install_scheduled_tasks.ps1

.EXAMPLE
powershell -ExecutionPolicy Bypass -File scripts\install_scheduled_tasks.ps1 -Remove
#>

[CmdletBinding()]
param(
    [switch]$Remove,
    [switch]$Enable
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$TaskNames = @("Observatory SE sweep", "Observatory BA sweep")

function Remove-Tasks {
    foreach ($name in $TaskNames) {
        $existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        if ($null -eq $existing) {
            Write-Output "not installed: $name"
            continue
        }
        if ($existing.State -eq "Running") {
            Stop-ScheduledTask -TaskName $name
            Write-Output "stopped running task: $name"
        }
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        Write-Output "unregistered: $name"
    }
}

if ($Remove) {
    Remove-Tasks
    exit 0
}

$make = Get-Command make -ErrorAction SilentlyContinue
if ($null -eq $make) {
    Write-Error "make was not found on PATH; the scheduled tasks cannot run without it"
}
$MakePath = $make.Source

function New-TaskSettings {
    New-ScheduledTaskSettingsSet -StartWhenAvailable `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -WakeToRun `
        -ExecutionTimeLimit (New-TimeSpan -Hours 4) `
        -MultipleInstances IgnoreNew
}

# S4U: runs whether the user is logged on or not, without storing a password
# and without elevation. Some configurations refuse the registration; Interactive
# (runs only when logged on, including locked) is the fallback - both register
# without elevation for the owning user.
function Register-TaskUnelevated {
    param(
        [string]$Name,
        [object]$Action,
        [object[]]$Triggers,
        [object]$Settings
    )
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U -RunLevel Limited
    try {
        Register-ScheduledTask -TaskName $Name -Action $Action -Trigger $Triggers `
            -Settings $Settings -Principal $principal | Out-Null
        Write-Output "  principal: S4U (runs whether logged on or not)"
        return
    } catch {
        Write-Output "  S4U registration refused ($($_.Exception.Message)); using Interactive"
    }
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $Name -Action $Action -Trigger $Triggers `
        -Settings $Settings -Principal $principal | Out-Null
    Write-Output "  principal: Interactive (runs when logged on, including locked)"
}

function Register-Task {
    param(
        [string]$Name,
        [string]$Sources,
        [object[]]$Triggers
    )
    $action = New-ScheduledTaskAction -Execute $MakePath -Argument "auto SOURCES=$Sources" -WorkingDirectory $RepoRoot
    $existing = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    if ($null -ne $existing) {
        Unregister-ScheduledTask -TaskName $Name -Confirm:$false
        Write-Output "replaced existing task: $Name"
    }
    Register-TaskUnelevated -Name $Name -Action $action -Triggers $Triggers -Settings (New-TaskSettings)
    if (-not $Enable) {
        Disable-ScheduledTask -TaskName $Name | Out-Null
    }
    $task = Get-ScheduledTask -TaskName $Name
    $info = $task | Get-ScheduledTaskInfo
    Write-Output ("installed: {0} [{1}] - make auto SOURCES={2} (repo: {3})" -f `
        $Name, $task.State, $Sources, $RepoRoot)
    Write-Output ("  next run: {0}" -f $(if ($info.NextRunTime) { $info.NextRunTime } else { "(disabled or no next run)" }))
}

Register-Task -Name $TaskNames[0] -Sources "jobtech" -Triggers @(
    (New-ScheduledTaskTrigger -Daily -At "07:30"),
    (New-ScheduledTaskTrigger -Daily -At "19:30")
)

Register-Task -Name $TaskNames[1] -Sources "ba" -Triggers @(
    (New-ScheduledTaskTrigger -Daily -At "13:00")
)

if (-not $Enable) {
    Write-Output ""
    Write-Output "Both tasks are registered DISABLED. Enabling is one command away:"
    Write-Output '  Get-ScheduledTask "Observatory SE sweep", "Observatory BA sweep" | Enable-ScheduledTask'
}
