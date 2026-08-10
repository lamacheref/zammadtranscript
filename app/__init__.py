from pathlib import Path

APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "_data"
DATA_DIR.mkdir(exist_ok=True)