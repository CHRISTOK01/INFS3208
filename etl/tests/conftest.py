import sys
from pathlib import Path

# Let the tests import usda.py from the etl folder
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
