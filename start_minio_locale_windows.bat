@echo off
cd /d %~dp0
setlocal

echo ==========================================
echo   GiroFacile - Archivio POD locale MinIO
echo ==========================================
echo.

docker version >nul 2>&1
if errorlevel 1 (
  echo ERRORE: Docker Desktop non disponibile.
  echo Avvia Docker Desktop e riprova.
  pause
  exit /b 1
)

echo Avvio MinIO e preparazione bucket locale...
docker compose --profile local-storage up -d minio minio-init
if errorlevel 1 (
  echo.
  echo ERRORE durante l'avvio di MinIO.
  echo Controlla Docker Desktop e il file docker-compose.yml.
  pause
  exit /b 1
)

echo.
echo MinIO locale avviato.
echo API S3:     http://127.0.0.1:9000
echo Console:    http://127.0.0.1:9001
echo Bucket:     girofacile-pod-local
echo.
echo Ora puoi avviare GiroFacile normalmente.
echo.
pause
