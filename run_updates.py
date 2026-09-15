import subprocess
import sys
from pathlib import Path


def run(cmd):
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        sys.exit(result.returncode)


def main():
    root = Path(__file__).resolve().parent

    # Step 1: Determine physics parameters and ideal design point
    run([sys.executable, str(root / "main_optimizer.py")])

    # Step 2: Convert physics -> Fusion 360 parameters
    run([sys.executable, str(root / "physics_to_fusion_params.py")])

    # Step 3: If Fusion BOM exists, rebuild report with BOM source-of-truth
    fusion_bom = root / "DFD_fusion360" / "DFD_Thruster_Materials_Stats.csv"
    if fusion_bom.exists():
        run([sys.executable, str(root / "main_optimizer.py")])
    else:
        print("Fusion BOM not found. Run Fusion 360 script, then rerun updates.")

    print("All updates complete.")


if __name__ == "__main__":
    main()
