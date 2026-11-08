@echo off
rem BGE-Remix P11: the RTX run on this PC (RTX graphics card, the real RTX
rem Remix runtime): motion trails, softness and sharing the graphics card,
rem measured in Remix. Game windows open and close by themselves: leave the
rem PC alone until this window says it has finished (about half an hour).
python "%~dp0..\run_local.py" p11rtx
echo.
pause
