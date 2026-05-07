# FFmpeg Installation for Windows

## Option 1: Manual Download (Fastest)

1. Download the full build from GitHub:
   https://github.com/GyanD/codexffmpeg/releases/download/8.1.1/ffmpeg-8.1.1-full_build.zip

2. Extract it to a folder, e.g.:
   C:\ffmpeg\

3. Add to your PATH environment variable:
   - Open System Properties (Win+Pause/Break or search "environment variables")
   - Edit system environment variables → Environment Variables
   - Under "System variables", find "Path" and click Edit
   - Add: C:\ffmpeg\bin
   - Click OK and restart your terminal

4. Verify:
   ffmpeg -version
   ffprobe -version

## Option 2: Chocolatey (if installed)

```powershell
choco install ffmpeg
```

## Option 3: Scoop (if installed)

```powershell
scoop install ffmpeg
```

## Option 4: Use Local Path in .env

If you don't want to add to PATH, extract FFmpeg to your project and set in `.env`:

```
FFMPEG_PATH=C:\full\path\to\ffmpeg.exe
FFPROBE_PATH=C:\full\path\to\ffprobe.exe
```

Then skip the PATH steps.
