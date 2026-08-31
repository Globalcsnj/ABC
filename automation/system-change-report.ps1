# ABC MoneyLoan - "What Changed on This PC" report
# ---------------------------------------------------------------------------
# Reads Windows' own built-in records and writes a plain-English report of the
# recent changes to THIS computer that could affect printers or other functions
# - whether someone did it at the keyboard or connected in remotely.
#
# It only READS. It never changes any setting, driver, or file.
#
# Run it by double-clicking system-change-report.bat (which runs this as admin
# so it can also read the sign-in history).
# ---------------------------------------------------------------------------

param(
    # How many days back to look. Change to 30 for a longer history.
    [int]$Days = 14
)

$ErrorActionPreference = "Continue"
$since = (Get-Date).AddDays(-$Days)

# Save the report to the Desktop with a timestamp so old ones are kept.
$stamp   = Get-Date -Format "yyyy-MM-dd_HHmm"
$desktop = [Environment]::GetFolderPath("Desktop")
$outFile = Join-Path $desktop "PC-Changes-$stamp.txt"

# Collect everything into one string, then show it AND save it.
$report = New-Object System.Text.StringBuilder
function Line($t = "") { [void]$report.AppendLine($t) }
function Section($t) {
    Line ""
    Line ("=" * 70)
    Line ("  $t")
    Line ("=" * 70)
}

Line "ABC MoneyLoan - What Changed on This PC"
Line ("Computer : {0}" -f $env:COMPUTERNAME)
Line ("Generated: {0}" -f (Get-Date -Format "yyyy-MM-dd HH:mm"))
Line ("Covering : the last {0} days (since {1})" -f $Days, $since.ToString("yyyy-MM-dd"))
Line "Note     : 'Remote' below means someone connected in over the network,"
Line "           not sitting at this computer."

# --- 1. Is remote-access even possible on this PC? -------------------------
Section "1. REMOTE-ACCESS TOOLS ON THIS PC"
try {
    $rdp = (Get-ItemProperty "HKLM:\System\CurrentControlSet\Control\Terminal Server" -Name fDenyTSConnections -ErrorAction Stop).fDenyTSConnections
    if ($rdp -eq 0) {
        Line "[!] Windows Remote Desktop (RDP) is TURNED ON - people can remote in."
    } else {
        Line "[ok] Windows Remote Desktop (RDP) is turned off."
    }
} catch { Line "( Could not read the Remote Desktop setting. )" }

$remoteApps = @{
    "TeamViewer"            = "TeamViewer.exe"
    "AnyDesk"               = "AnyDesk.exe"
    "RustDesk"              = "rustdesk.exe"
    "Chrome Remote Desktop" = "remoting_host.exe"
    "LogMeIn"               = "LogMeIn.exe"
    "UltraViewer"           = "UltraViewer_Desktop.exe"
    "Splashtop"             = "SRServer.exe"
}
$foundAny = $false
foreach ($name in $remoteApps.Keys) {
    $exe = $remoteApps[$name]
    $installed = Get-ChildItem "C:\Program Files","C:\Program Files (x86)" -Recurse -Filter $exe -ErrorAction SilentlyContinue | Select-Object -First 1
    $running   = Get-Process -Name ([IO.Path]::GetFileNameWithoutExtension($exe)) -ErrorAction SilentlyContinue
    if ($installed -or $running) {
        $foundAny = $true
        $state = if ($running) { "INSTALLED and RUNNING NOW" } else { "installed" }
        Line ("[!] {0} is {1}." -f $name, $state)
    }
}
if (-not $foundAny) { Line "[ok] No common remote-control apps (TeamViewer, AnyDesk, etc.) found." }

# --- 2. Who signed in, and was it local or remote? ------------------------
Section "2. SIGN-INS (last $Days days) - local vs remote"
Line "Logon types: 'at the keyboard' = someone here; 'REMOTE (network)' = remoted in."
Line ""
try {
    $logons = Get-WinEvent -FilterHashtable @{ LogName='Security'; Id=4624; StartTime=$since } -ErrorAction Stop
    $rows = foreach ($e in $logons) {
        $x = [xml]$e.ToXml()
        $d = @{}
        foreach ($n in $x.Event.EventData.Data) { $d[$n.Name] = $n.'#text' }
        $type = switch ($d['LogonType']) {
            '2'  { 'at the keyboard' }
            '7'  { 'unlocked screen' }
            '10' { 'REMOTE (Remote Desktop)' }
            '3'  { 'REMOTE (network/file share)' }
            '11' { 'at the keyboard (cached)' }
            default { "type $($d['LogonType'])" }
        }
        # Skip noisy system/service accounts.
        if ($d['TargetUserName'] -match '^(SYSTEM|LOCAL SERVICE|NETWORK SERVICE|DWM-|UMFD-|ANONYMOUS.*)') { continue }
        [PSCustomObject]@{
            When = $e.TimeCreated.ToString("MM/dd HH:mm")
            User = $d['TargetUserName']
            How  = $type
            From = if ($d['IpAddress'] -and $d['IpAddress'] -ne '-') { $d['IpAddress'] } else { $d['WorkstationName'] }
        }
    }
    if ($rows) {
        $rows | Select-Object -First 60 | Format-Table -AutoSize | Out-String | ForEach-Object { Line $_ }
        if ($rows | Where-Object { $_.How -like 'REMOTE*' }) {
            Line "[!] There WERE remote sign-ins in this period (see 'REMOTE' rows above)."
        } else {
            Line "[ok] No remote sign-ins found - all activity was at the keyboard."
        }
    } else { Line "No sign-in records in this period." }
} catch {
    Line "( Could not read the sign-in history. Run this report as administrator )"
    Line "( - the .bat launcher does that for you. )"
}

# --- 3. The big one: Windows' own reliability timeline --------------------
Section "3. INSTALLS, DRIVER CHANGES & FAILURES (Windows Reliability history)"
Line "This is the same list you'd see in Windows' 'Reliability Monitor'."
Line ""
try {
    $rel = Get-CimInstance -ClassName Win32_ReliabilityRecords -ErrorAction Stop |
           Where-Object { $_.TimeGenerated -ge $since } |
           Sort-Object TimeGenerated -Descending
    if ($rel) {
        foreach ($r in $rel | Select-Object -First 80) {
            $msg = ($r.Message -replace '\s+', ' ').Trim()
            if ($msg.Length -gt 90) { $msg = $msg.Substring(0,90) + "..." }
            Line ("{0}  |  {1}  |  {2}" -f $r.TimeGenerated.ToString("MM/dd HH:mm"), $r.ProductName, $msg)
        }
    } else { Line "No reliability records in this period." }
} catch { Line "( Could not read the reliability history. )" }

# --- 4. Recently installed / updated programs -----------------------------
Section "4. PROGRAMS INSTALLED OR UPDATED (last $Days days)"
try {
    $keys = @(
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )
    $apps = Get-ItemProperty $keys -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -and $_.InstallDate } |
        ForEach-Object {
            $dt = $null
            [void][DateTime]::TryParseExact($_.InstallDate,"yyyyMMdd",$null,'None',[ref]$dt)
            if ($dt -and $dt -ge $since) {
                [PSCustomObject]@{ Date = $dt.ToString("yyyy-MM-dd"); Program = $_.DisplayName; Version = $_.DisplayVersion }
            }
        } | Sort-Object Date -Descending
    if ($apps) { $apps | Format-Table -AutoSize | Out-String | ForEach-Object { Line $_ } }
    else { Line "No newly installed programs recorded in this period." }
} catch { Line "( Could not read installed programs. )" }

# --- 5. Windows updates -----------------------------------------------------
Section "5. WINDOWS UPDATES INSTALLED (last $Days days)"
try {
    $hf = Get-HotFix -ErrorAction Stop | Where-Object { $_.InstalledOn -and $_.InstalledOn -ge $since } |
          Sort-Object InstalledOn -Descending
    if ($hf) {
        $hf | Select-Object @{n='Date';e={$_.InstalledOn.ToString("yyyy-MM-dd")}}, HotFixID, Description |
            Format-Table -AutoSize | Out-String | ForEach-Object { Line $_ }
    } else { Line "No Windows updates installed in this period." }
} catch { Line "( Could not read Windows update history. )" }

# --- 6. Printers: current list + recent printer events --------------------
Section "6. PRINTERS - current status and recent changes"
try {
    Line "Printers currently set up on this PC:"
    Get-Printer -ErrorAction Stop | Select-Object Name, DriverName, PortName,
        @{n='Status';e={$_.PrinterStatus}} | Format-Table -AutoSize | Out-String | ForEach-Object { Line $_ }
} catch { Line "( Could not list printers. )" }

Line ""
Line "Recent printer events (added/removed/driver/errors):"
$printLogs = @('Microsoft-Windows-PrintService/Admin','Microsoft-Windows-PrintService/Operational')
$gotPrint = $false
foreach ($log in $printLogs) {
    try {
        $pe = Get-WinEvent -FilterHashtable @{ LogName=$log; StartTime=$since } -ErrorAction Stop |
              Sort-Object TimeCreated -Descending | Select-Object -First 25
        foreach ($e in $pe) {
            $gotPrint = $true
            $m = ($e.Message -replace '\s+', ' ').Trim()
            if ($m.Length -gt 100) { $m = $m.Substring(0,100) + "..." }
            Line ("{0}  |  {1}" -f $e.TimeCreated.ToString("MM/dd HH:mm"), $m)
        }
    } catch { }
}
if (-not $gotPrint) {
    Line "No printer events recorded. (The detailed printer log may be off; that's normal.)"
    Line "Tip: to record every future printer change, open 'Event Viewer' ->"
    Line "     Applications and Services Logs -> Microsoft -> Windows -> PrintService"
    Line "     -> Operational -> right-click -> Enable Log."
}

# --- Save + show ----------------------------------------------------------
$text = $report.ToString()
try { $text | Out-File -FilePath $outFile -Encoding UTF8 } catch {}
Write-Host $text
Write-Host ""
Write-Host ("Saved a copy to: {0}" -f $outFile) -ForegroundColor Green
