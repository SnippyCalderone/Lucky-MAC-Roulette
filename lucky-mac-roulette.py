# Lucky MAC Roulette — CLI v0.1
# Windows-only (uses PowerShell cmdlets to set NIC MAC)
# Requires: Python 3.9+, tqdm, Ookla Speedtest CLI (speedtest.exe)

import os, sys, json, time, subprocess, random, string, csv, shutil, socket, signal
from datetime import datetime
from pathlib import Path
from tqdm import tqdm

# -------------------- CONFIG --------------------
PROJECT_DIR = Path(r"C:\Users\zachp\Desktop\MAC-Cycle-Tool")
PROFILE_PATH = PROJECT_DIR / "mac_profile.json"
RESULTS_CSV = PROJECT_DIR / "results.csv"
SPEEDTEST_EXE = (Path(__file__).parent / "speedtest.exe")  # fallback: local folder
ADAPTER_NAME = "Ethernet"  # change if needed
TRIES_PER_MAC = 1          # do 2-3 if your results are noisy
WAIT_ONLINE_TIMEOUT = 45
# ------------------------------------------------

BANNER = r"""
 _          _            __  __     _      __  __     _       ____            _       _ _      
| |    __ _| | _____   _\ \/ /___ | | ___|  \/  |___| |_    |  _ \ ___  _ __(_)_ __ (_) |_ ___
| |   / _` | |/ / _ \ / _ \  // _ \| |/ _ \ |\/| / __| __|   | |_) / _ \| '__| | '_ \| | __/ _ \
| |__| (_| |   < (_) |  __/ . \ (_) | |  __/ |  | \__ \ |_    |  _ < (_) | |  | | | | | | ||  __/
|_____\__,_|_|\_\___/ \___/_/\_\___/|_|\___|_|  |_|___/\__|   |_| \_\___/|_|  |_|_| |_|_|\__\___|
                                      by Big Dawg & Spanky  (v0.1 CLI)
"""

def ensure_dirs():
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)

def run_ps(cmd):
    """Run a PowerShell command and return (rc, stdout, stderr)."""
    full = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", cmd]
    proc = subprocess.Popen(full, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = proc.communicate()
    return proc.returncode, out.strip(), err.strip()

def get_effective_mac():
    rc, out, err = run_ps(f'Get-NetAdapter -Name "{ADAPTER_NAME}" | Select -ExpandProperty MacAddress')
    return out.replace(":", "").replace("-", "").strip()

def get_true_mac():
    # PermanentAddress from WMI; fallback to current MAC if missing
    ps = r"""Get-WmiObject -Class Win32_NetworkAdapter -Filter "NetEnabled=true" |
    Where-Object {$_.Name -match 'Realtek|Ethernet'} | Select -ExpandProperty PermanentAddress"""
    rc, out, err = run_ps(ps)
    mac = out.strip().replace(":", "").replace("-", "")
    return mac if mac else get_effective_mac()

def get_override_value():
    rc, out, err = run_ps(f'Get-NetAdapterAdvancedProperty -Name "{ADAPTER_NAME}" -DisplayName "Network Address" | Select -ExpandProperty DisplayValue')
    # Returns "Not Present" or 12-hex string
    return out.strip() if out else "Not Present"

def set_override_value(mac_or_not_present):
    cmd = f'Set-NetAdapterAdvancedProperty -Name "{ADAPTER_NAME}" -DisplayName "Network Address" -DisplayValue "{mac_or_not_present}" -NoRestart'
    return run_ps(cmd)

def disable_enable_adapter():
    run_ps(f'Disable-NetAdapter -Name "{ADAPTER_NAME}" -Confirm:$false')
    time.sleep(3)
    run_ps(f'Enable-NetAdapter -Name "{ADAPTER_NAME}" -Confirm:$false')

def wait_online(timeout=WAIT_ONLINE_TIMEOUT):
    # simple connectivity wait: ping + DNS resolve
    start = time.time()
    with tqdm(total=timeout, desc="Waiting for network", leave=False) as bar:
        while time.time() - start < timeout:
            ok_ping = False
            ok_dns = False
            try:
                # ping 1.1.1.1 once
                rc = subprocess.call(["ping", "-n", "1", "1.1.1.1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                ok_ping = (rc == 0)
            except Exception:
                pass
            try:
                socket.gethostbyname("google.com")
                ok_dns = True
            except Exception:
                ok_dns = False
            if ok_ping and ok_dns:
                return True
            time.sleep(1)
            bar.update(1)
    return False

def gen_mac():
    # Locally administered, unicast: set 2nd least significant bit of first octet
    first = 0x02
    rest = [random.randint(0,255) for _ in range(5)]
    return "".join(f"{b:02X}" for b in [first] + rest)

def run_speedtest():
    exe = shutil.which("speedtest") or (SPEEDTEST_EXE if SPEEDTEST_EXE.exists() else None)
    if not exe:
        return None
    # Accept license/GDPR every time to avoid first-run prompt issues
    try:
        proc = subprocess.run([str(exe), "--accept-license", "--accept-gdpr", "-f", "json"],
                              capture_output=True, text=True, timeout=120)
        if proc.returncode != 0 or not proc.stdout:
            return None
        import json as _json
        data = _json.loads(proc.stdout)
        down = round(data["download"]["bandwidth"] * 8 / (1024*1024), 1)  # bytes/s -> Mbps
        up   = round(data["upload"]["bandwidth"]   * 8 / (1024*1024), 1)
        lat  = round(data["ping"]["latency"], 1)
        return {"down": down, "up": up, "lat": lat}
    except Exception:
        return None

def append_csv(row):
    new_file = not RESULTS_CSV.exists()
    with RESULTS_CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["timestamp","mac","download_mbps","upload_mbps","latency_ms"])
        w.writerow(row)

def load_profile():
    if PROFILE_PATH.exists():
        with PROFILE_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_profile(profile):
    with PROFILE_PATH.open("w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)

def apply_mac(mac_value):
    set_override_value(mac_value)
    disable_enable_adapter()
    ok = wait_online()
    return ok

def choose_count():
    print("\nHow many MACs to test?")
    print("[1] 10   [2] 25   [3] 50   [4] Custom")
    while True:
        sel = input("> ").strip()
        if sel == "1": return 10
        if sel == "2": return 25
        if sel == "3": return 50
        if sel == "4":
            while True:
                try:
                    n = int(input("Enter custom integer (e.g., 75): ").strip())
                    if n > 0: return n
                except ValueError:
                    pass
                print("Invalid number. Try again.")
        print("Pick 1, 2, 3, or 4.")

def post_menu(best):
    print("\n=== Post-Run Actions ===")
    print(f"Best MAC: {best['mac']}  ↓{best['down']}  ↑{best['up']}  ping {best['lat']}")
    print("[1] Apply Best MAC")
    print("[2] Revert to Start MAC")
    print("[3] Revert to True Hardware MAC")
    print("[4] Exit (auto-revert to Start if no changes made)")
    while True:
        choice = input("> ").strip()
        if choice in {"1","2","3","4"}:
            return choice
        print("Pick 1–4.")

def main():
    os.system("cls")
    print(BANNER)
    ensure_dirs()

    # Capture starting/true MAC & current override
    true_mac = get_true_mac()
    start_effective = get_effective_mac()
    start_override = get_override_value()  # "Not Present" or a 12-hex string

    profile = {
        "true_mac": true_mac,
        "start_effective": start_effective,
        "start_override": start_override,
        "adapter": ADAPTER_NAME,
        "started_at": datetime.now().isoformat(timespec="seconds")
    }
    save_profile(profile)

    # Pick count
    count = choose_count()
    print(f"\nTesting {count} random MACs... (adapter: {ADAPTER_NAME})")
    changed_by_user = False
    tested = []

    try:
        with tqdm(total=count, desc="Cycling MACs", ncols=80) as pbar:
            for i in range(count):
                mac = gen_mac()
                # Set MAC
                ok_apply = apply_mac(mac)
                if not ok_apply:
                    append_csv([datetime.now().isoformat(timespec="seconds"), mac, "", "", ""])
                    tested.append({"mac": mac, "down": -1, "up": -1, "lat": 9999})
                    pbar.update(1)
                    continue

                # Run speedtest (optionally multiple times, keep best)
                best_res = None
                for _ in range(TRIES_PER_MAC):
                    with tqdm(total=1, desc="Running speed test", leave=False) as sbar:
                        res = run_speedtest()
                        sbar.update(1)
                    if res:
                        if best_res is None or res["down"] > best_res["down"]:
                            best_res = res
                    time.sleep(0.5)

                if best_res:
                    append_csv([datetime.now().isoformat(timespec="seconds"), mac, best_res["down"], best_res["up"], best_res["lat"]])
                    tested.append({"mac": mac, **best_res})
                else:
                    append_csv([datetime.now().isoformat(timespec="seconds"), mac, "", "", ""])
                    tested.append({"mac": mac, "down": -1, "up": -1, "lat": 9999})

                pbar.update(1)

        # Pick best by download
        valid = [t for t in tested if t["down"] >= 0]
        if valid:
            best = max(valid, key=lambda r: r["down"])
        else:
            best = {"mac": None, "down": -1, "up": -1, "lat": 9999}

        # Post-run actions
        choice = post_menu(best)
        if choice == "1" and best["mac"]:
            print(f"Applying Best MAC: {best['mac']}")
            apply_mac(best["mac"])
            changed_by_user = True
        elif choice == "2":
            print(f"Reverting to Start MAC setting: {profile['start_override']}")
            apply_mac(profile["start_override"] if profile["start_override"] != "" else "Not Present")
        elif choice == "3":
            print(f"Reverting to True Hardware MAC: {profile['true_mac']}")
            apply_mac("Not Present")  # Not Present forces hardware MAC
        elif choice == "4":
            pass  # handled in finally

    finally:
        # Auto-revert if user didn't commit a change
        if not changed_by_user:
            print("Auto-reverting to Start MAC...")
            apply_mac(profile["start_override"] if profile["start_override"] != "" else "Not Present")
        print("\nSession complete. Results at:", RESULTS_CSV)
        profile["ended_at"] = datetime.now().isoformat(timespec="seconds")
        save_profile(profile)

if __name__ == "__main__":
    # Graceful Ctrl+C: still auto-revert in finally
    signal.signal(signal.SIGINT, signal.default_int_handler)
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        # Let finally run in main()