@echo off
setlocal

call "C:\BuildTools\Common7\Tools\VsDevCmd.bat" -host_arch=x64 -arch=x64 >nul

set "WindowsSdkDir=C:\Program Files (x86)\Windows Kits\10\"
set "WindowsSDKVersion=10.0.26100.0\"
set "PATH=C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64;%PATH%"
set "INCLUDE=C:\BuildTools\VC\Tools\MSVC\14.44.35207\include;C:\BuildTools\VC\Auxiliary\VS\include;C:\Program Files (x86)\Windows Kits\10\include\10.0.26100.0\ucrt;C:\Program Files (x86)\Windows Kits\10\include\10.0.26100.0\um;C:\Program Files (x86)\Windows Kits\10\include\10.0.26100.0\shared;C:\Program Files (x86)\Windows Kits\10\include\10.0.26100.0\winrt;C:\Program Files (x86)\Windows Kits\10\include\10.0.26100.0\cppwinrt"
set "LIB=C:\BuildTools\VC\Tools\MSVC\14.44.35207\lib\x64;C:\Program Files (x86)\Windows Kits\10\lib\10.0.26100.0\ucrt\x64;C:\Program Files (x86)\Windows Kits\10\lib\10.0.26100.0\um\x64"
set "LIBPATH=%LIB%"
set "DISTUTILS_USE_SDK=1"
set "MSSdk=1"

where rc
where cl

python -m pip install --no-use-pep517 git+https://github.com/lyst/lightfm.git
