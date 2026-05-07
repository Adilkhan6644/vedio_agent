@echo off
REM Download and extract FFmpeg to local project folder
REM This avoids admin rights and PATH issues

echo Downloading FFmpeg...
powershell -Command "[ System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor [System.Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://github.com/GyanD/codexffmpeg/releases/download/8.1.1/ffmpeg-8.1.1-full_build.zip' -OutFile 'ffmpeg-8.1.1.zip' -UseBasicParsing"

if errorlevel 1 (
    echo Failed to download FFmpeg
    exit /b 1
)

echo Extracting FFmpeg...
powershell -Command "Expand-Archive -Path 'ffmpeg-8.1.1.zip' -DestinationPath '.'"

if errorlevel 1 (
    echo Failed to extract FFmpeg
    exit /b 1
)

REM Rename extracted folder to 'ffmpeg'
for /d %%D in (ffmpeg-*) do (
    echo Found folder: %%D
    ren "%%D" ffmpeg
)

echo Cleanup...
del ffmpeg-8.1.1.zip

echo.
echo FFmpeg extracted to: %CD%\ffmpeg
echo.
echo Add this to .env:
echo FFMPEG_PATH=%CD%\ffmpeg\bin\ffmpeg.exe
echo FFPROBE_PATH=%CD%\ffmpeg\bin\ffprobe.exe
echo.
echo Done!
