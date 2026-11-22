$CliArgs = @($args)
& (Join-Path $PSScriptRoot 'python_local.ps1') -m room_walls @CliArgs
exit $LASTEXITCODE
