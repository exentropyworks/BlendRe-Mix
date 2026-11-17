@echo off
rem BGE-Remix P12: the RTX run on this PC (RTX graphics card, the real RTX
rem Remix runtime): the room and the room imported from its capture, side
rem by side in Remix. Game windows open and close by themselves: leave the
rem PC alone until this window says it has finished (a few minutes).
python "%~dp0..\run_local.py" p12rtx
echo.
pause
