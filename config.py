import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "data" / "raw"
load_dotenv(BASE_DIR / ".env")
DATABASE_URL = os.getenv("DATABASE_URL", "")

FEEDS = {
    "extraurbano": "https://www.stpbrindisi.it/attachments/article/963/Extraurbano.zip",
    "brindisi": "https://www.stpbrindisi.it/attachments/article/963/Urbano_Brindisi.zip",
    "ostuni": "https://www.stpbrindisi.it/attachments/article/963/Urbano_Ostuni.zip",
    "francavilla": "https://www.stpbrindisi.it/attachments/article/963/Urbano_Francavilla.zip",
}
