@echo off
echo Starting... > debug.log
date /t >> debug.log
time /t >> debug.log
git status >> debug.log 2>&1
git checkout StableV2 >> debug.log 2>&1
git push >> debug.log 2>&1
echo Done. >> debug.log
