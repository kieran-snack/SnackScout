# Creates "SnackScout Launcher" shortcuts on the Desktop and in the Start menu that open the launcher.
# Run once (or again after moving the folder):  powershell -ExecutionPolicy Bypass -File launcher\make_shortcuts.ps1
$root = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $root ".venv\Scripts\pythonw.exe"
$script = Join-Path $root "SnackScout Launcher.pyw"
$icon = Join-Path $root "launcher\icon.ico"
if (-not (Test-Path $pythonw)) { Write-Error "Run SnackScout.bat once first to set up Python."; exit 1 }

$shell = New-Object -ComObject WScript.Shell
$places = @([Environment]::GetFolderPath("Desktop"), (Join-Path ([Environment]::GetFolderPath("Programs")) ""))
foreach ($dir in $places) {
  $old = Join-Path $dir "SnackScout.lnk"   # shortcuts from before the rename
  if (Test-Path $old) { Remove-Item $old }
  $lnk = $shell.CreateShortcut((Join-Path $dir "SnackScout Launcher.lnk"))
  $lnk.TargetPath = $pythonw
  $lnk.Arguments = "`"$script`""
  $lnk.WorkingDirectory = $root
  $lnk.IconLocation = "$icon,0"
  $lnk.Description = "SnackScout Launcher - Team 34672 scouting"
  $lnk.Save()
  Write-Output "Created $($lnk.FullName)"
}
