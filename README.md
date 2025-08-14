echo "# Lucky MAC Roulette" > README.md
echo "" >> README.md
echo "Automates cycling randomized locally-administered MAC addresses and runs Ookla Speedtest to find the fastest profile. Auto-revert safety included." >> README.md
echo "" >> README.md
echo "## Quick start" >> README.md
echo "1. Install Python 3.9+ and Ookla speedtest.exe" >> README.md
echo "2. python -m venv venv && .\\venv\\Scripts\\activate" >> README.md
echo "3. pip install -r requirements.txt" >> README.md
echo "4. python lucky-mac-roulette.py" >> README.md

git add README.md
git commit -m "Add README"
git push