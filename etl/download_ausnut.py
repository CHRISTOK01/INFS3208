"""Download the Australian food data that MacroScope uses.

    python etl/download_ausnut.py           # about 14 MB
    python etl/download_ausnut.py --force   # download again even if the files are there

It saves four Excel files into etl/data/ausnut/:
  - AUSNUT 2023 food details, nutrient profiles and food measures (from the "All files" zip)
  - AFCD Release 3 nutrient profiles, which we only use for copper, manganese and pantothenic acid,
    because AUSNUT doesn't include them

Where the data comes from: Food Standards Australia New Zealand (FSANZ).
  AUSNUT 2023: https://www.foodstandards.gov.au/science-data/food-nutrient-databases/ausnut/data-files
  AFCD:        https://www.foodstandards.gov.au/science-data/food-nutrient-databases/afcd/data-files
Licence: Creative Commons Attribution 4.0 (CC BY 4.0). We must say the data is from FSANZ.

Like download_usda.py, it only uses Python's built-in libraries.
"""
import argparse
import shutil
import sys
import zipfile
from pathlib import Path

from download_usda import download

BASE_URL = "https://www.foodstandards.gov.au/sites/default/files/"
AUSNUT_ZIP = "2026-03/AUSNUT%202023%20-%20All%20Files_0.zip"
AFCD_FILE = "2025-12/AFCD%20Release%203%20-%20Nutrient%20profiles.xlsx"

# The files we need from inside the AUSNUT zip (it has 16)
AUSNUT_FILES = [
    "AUSNUT 2023 - Food details.xlsx",
    "AUSNUT 2023 - Food nutrient profiles.xlsx",
    "AUSNUT 2023 - Food measures.xlsx",
]
AFCD_NAME = "AFCD Release 3 - Nutrient profiles.xlsx"

FOLDER = Path(__file__).resolve().parent / "data" / "ausnut"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="download again even if the files are already there")
    args = parser.parse_args()
    FOLDER.mkdir(parents=True, exist_ok=True)

    if all((FOLDER / name).exists() for name in AUSNUT_FILES) and not args.force:
        print(f"- AUSNUT 2023: already in {FOLDER}, skipping (use --force to download again)")
    else:
        zip_path = FOLDER / "ausnut.zip"
        print("- AUSNUT 2023: downloading")
        download(BASE_URL + AUSNUT_ZIP, zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.infolist():
                name = Path(member.filename).name    # drop the folder inside the zip
                if name in AUSNUT_FILES:
                    with zf.open(member) as src, open(FOLDER / name, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        zip_path.unlink()

    if (FOLDER / AFCD_NAME).exists() and not args.force:
        print(f"- AFCD Release 3: already in {FOLDER}, skipping")
    else:
        print("- AFCD Release 3: downloading")
        download(BASE_URL + AFCD_FILE, FOLDER / AFCD_NAME)

    print("\nFiles in etl/data/ausnut:")
    for path in sorted(FOLDER.glob("*.xlsx")):
        print(f"  {path.name}  ({path.stat().st_size / 2**20:.1f} MB)")


if __name__ == "__main__":
    sys.exit(main())
