@echo off
REM MARK XXXIX — launch the read-only team dashboard.
REM Reads logs\audit.db (the black box) + config\agents.json. Safe to run anytime;
REM it only watches, it never commands.
cd /d "%~dp0"
streamlit run dashboard\app.py --server.headless true
