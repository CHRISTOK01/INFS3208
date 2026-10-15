"""Download the USDA FoodData Central CSV files that MacroScope uses, and unzip them.

The data is public and very large, so it isn't kept in git. Run this script to get it instead:

    python etl/download_usda.py                 # everything, including Branded foods (about 440 MB)
    python etl/download_usda.py --skip-branded  # just the three main data sets (about 11 MB)

Each data set gets its own folder under etl/data/ (for example etl/data/foundation/food.csv),
because every zip has files with the same names in it. It only uses Python's built-in
libraries, so it runs anywhere: Windows, Mac, Linux, or inside a container.

Where the data comes from: https://fdc.nal.usda.gov/download-datasets (U.S. Department of
Agriculture, Agricultural Research Service, FoodData Central). It's public domain (CC0).
"""
import argparse
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

BASE_URL = "https://fdc.nal.usda.gov/fdc-datasets/"

# Folder name -> zip file. These are fixed releases, so every run loads exactly the same data.
DATASETS = {
    "foundation": "FoodData_Central_foundation_food_csv_2026-04-30.zip",  # ~3 MB, the most detailed vitamin and mineral data
    "sr_legacy": "FoodData_Central_sr_legacy_food_csv_2018-04.zip",      # ~5 MB, its last ever release (2018)
    "fndds": "FoodData_Central_survey_food_csv_2024-10-31.zip",           # ~3 MB, the newest FNDDS release
    "branded": "FoodData_Central_branded_food_csv_2026-04-30.zip",        # ~427 MB, supermarket labels and barcodes
}

DATA_DIR = Path(__file__).resolve().parent / "data"


def download(url: str, target: Path):
    """Save a file from the web to disk a piece at a time, showing progress every 25 MB or so."""
    with urllib.request.urlopen(url) as response, open(target, "wb") as out:
        total = int(response.headers.get("Content-Length", 0))
        done, next_report = 0, 0
        while chunk := response.read(1024 * 1024):
            out.write(chunk)
            done += len(chunk)
            if done >= next_report:
                print(f"    {done // 2**20} / {total // 2**20} MB", flush=True)
                next_report += 25 * 2**20


def extract_csvs(zip_path: Path, folder: Path):
    """Pull just the .csv files out of the zip and put them straight into `folder`.

    Any folders inside the zip are ignored.
    """
    folder.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            # Keep only the file name, dropping any folders. This also stops a "../" path
            # in the zip from writing outside etl/data.
            name = Path(member.filename).name
            if member.is_dir() or not name.lower().endswith(".csv"):
                continue
            with zf.open(member) as src, open(folder / name, "wb") as dst:
                shutil.copyfileobj(src, dst)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-branded", action="store_true", help="leave out the big (~427 MB) Branded foods data set")
    parser.add_argument("--force", action="store_true", help="download again even if the files are already there")
    args = parser.parse_args()

    for folder_name, zip_name in DATASETS.items():
        if folder_name == "branded" and args.skip_branded:
            print(f"- {folder_name}: skipped (--skip-branded)")
            continue

        folder = DATA_DIR / folder_name
        if (folder / "food.csv").exists() and not args.force:
            print(f"- {folder_name}: already in {folder}, skipping (use --force to download again)")
            continue

        zip_path = DATA_DIR / zip_name
        print(f"- {folder_name}: downloading {zip_name}")
        download(BASE_URL + zip_name, zip_path)
        print(f"  unzipping the CSV files into {folder}")
        extract_csvs(zip_path, folder)
        zip_path.unlink()   # we don't need the zip once it's unzipped

    print("\nFiles in etl/data:")
    for csv in sorted(DATA_DIR.glob("*/*.csv")):
        print(f"  {csv.relative_to(DATA_DIR)}  ({csv.stat().st_size / 2**20:.1f} MB)")


if __name__ == "__main__":
    sys.exit(main())
