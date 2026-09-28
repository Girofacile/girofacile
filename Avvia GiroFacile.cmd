@echo off
setlocal
title GiroFacile - Aggiorna e avvia
set "PROJECT=%USERPROFILE%\Documents\girofacile"
if not exist "%PROJECT%\avvia_aggiornato_windows.ps1" (
  echo ERRORE: progetto non trovato in "%PROJECT%".
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PROJECT%\avvia_aggiornato_windows.ps1"
if errorlevel 1 pause
