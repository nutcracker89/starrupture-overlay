@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
cd /d F:\sr_dump
echo --- compiling RecipeDumper.dll ---
cl /nologo /O2 /EHa /std:c++17 /LD recipe_dumper.cpp /link /OUT:rdf2.dll user32.lib
echo --- compiling inject.exe ---
cl /nologo /O2 /EHsc /std:c++17 inject.cpp /link /OUT:inject.exe
echo --- done ---
dir /b *.dll *.exe
