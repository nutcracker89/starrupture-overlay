@echo off
REM Build srextract.exe (the turnkey icon extractor) from source.
REM Requires: .NET 10 SDK + git. Clones CUE4Parse master (needed for UE5.6 support).
REM Most people DON'T need this — just download srextract.exe from the GitHub Release.

if not exist CUE4Parse (
  echo Cloning CUE4Parse master...
  git clone --depth 1 https://github.com/FabianFG/CUE4Parse.git CUE4Parse
)

dotnet publish -c Release -r win-x64 --self-contained true ^
  -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true ^
  -p:EnableCompressionInSingleFile=true -o publish

echo.
echo Done -^> publish\srextract.exe
pause
