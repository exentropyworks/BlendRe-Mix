@echo off
rem BGE-Remix P12: the RTX run on this PC (RTX graphics card, the real RTX
rem Remix runtime): this round, the C1 check (does Remix capture a BGE-Remix
rem scene?). A game window opens and closes by itself: leave the PC alone
rem until this window says it has finished (a few minutes).
python "%~dp0..\run_local.py" p12rtx
echo.
pause
