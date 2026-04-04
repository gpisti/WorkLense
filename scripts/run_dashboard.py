#!/usr/bin/env python3
"""Start the WorkLense Streamlit dashboard. Usage: python scripts/run_dashboard.py"""
import os
import subprocess
import sys

def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root)
    venv_python = os.path.join(root, ".venv", "bin", "python")
    python = venv_python if os.path.isfile(venv_python) else sys.executable
    subprocess.run(
        [python, "-m", "streamlit", "run", "streamlit_app.py", "--server.address=0.0.0.0"],
        cwd=root,
    )

if __name__ == "__main__":
    main()

# -----------------------------------------------------------------------------
# Gál István – szakdolgozat. A megvalósítás során mesterséges intelligencia (AI) eszközöket használtam.
