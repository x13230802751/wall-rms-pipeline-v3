$PythonArgs = @($args)
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskVenvPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
$taskBundledPython = 'C:\Program Files\WindowsApps\OpenAI.CodexPrimaryRuntime.v26-1119-907-0_26.1119.907.0_x64__3k8sg7r9htsxt\dependencies\python\python.exe'
if (Test-Path -LiteralPath $taskVenvPython) { $taskPython = $taskVenvPython }
elseif (Test-Path -LiteralPath $taskBundledPython) { $taskPython = $taskBundledPython }
else { $taskPython = (Get-Command python -ErrorAction Stop).Source }
$taskOldPythonPath = $env:PYTHONPATH
$taskOldThreads = $env:OPENBLAS_NUM_THREADS
$taskOldUtf8 = $env:PYTHONUTF8
try {
    $taskRuntime = $(if (Test-Path -LiteralPath $taskVenvPython) { '' } else { ";$taskRoot\.runtime" })
    $env:PYTHONPATH = "$taskRoot$taskRuntime" + $(if ($taskOldPythonPath) { ";$taskOldPythonPath" } else { '' })
    $env:OPENBLAS_NUM_THREADS = '1'
    $env:PYTHONUTF8 = '1'
    & $taskPython @PythonArgs
    $taskExit = $LASTEXITCODE
} finally {
    $env:PYTHONPATH = $taskOldPythonPath
    $env:OPENBLAS_NUM_THREADS = $taskOldThreads
    $env:PYTHONUTF8 = $taskOldUtf8
}
exit $taskExit
