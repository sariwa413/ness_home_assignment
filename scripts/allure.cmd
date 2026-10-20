@echo off
REM Serves the Allure report.
REM
REM Batch (not PowerShell) on purpose: this machine's execution policy is
REM AllSigned, which refuses unsigned .ps1 files - including npm's allure shim.
REM
REM Usage:
REM   scripts\allure.cmd            serve the latest results (opens a browser)
REM   scripts\allure.cmd generate   write a static report to artifacts\allure-report

setlocal

set "ROOT=%~dp0.."
set "RESULTS=%ROOT%\artifacts\allure-results"
set "REPORT=%ROOT%\artifacts\allure-report"

REM Locate a Java runtime for this session only (no machine-wide changes).
if not exist "%JAVA_HOME%\bin\java.exe" (
    for %%D in (
        "C:\Program Files\Java\jdk1.8.0_333"
        "C:\Program Files\Microsoft\jdk-17"
        "C:\Program Files\Eclipse Adoptium\jdk-17"
    ) do (
        if exist "%%~D\bin\java.exe" (
            set "JAVA_HOME=%%~D"
            goto :found
        )
    )
)
:found

if not exist "%JAVA_HOME%\bin\java.exe" (
    echo No Java runtime found. Install a JDK 8+ and retry.
    exit /b 1
)

set "PATH=%JAVA_HOME%\bin;%PATH%"

REM This network blocks Allure's usage-analytics call, which stalls the run with
REM socket retries. The report does not need it.
set "ALLURE_NO_ANALYTICS=1"
set "JAVA_OPTS=-Dallure.analytics.enabled=false %JAVA_OPTS%"

if /i "%~1"=="generate" (
    call allure.cmd generate "%RESULTS%" -o "%REPORT%" --clean
    echo Report written to %REPORT%
) else (
    call allure.cmd serve "%RESULTS%"
)

endlocal
