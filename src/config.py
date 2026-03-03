"""
Central configuration for the Historical Digital Edition pipeline.

Copy .env.example → .env and set GEMINI_API_KEY, then adjust the
constants below to match your project.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# API / Model
# ---------------------------------------------------------------------------

GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
MODEL_ID: str = "gemini-3-flash-preview"   # update as needed
THINKING_LEVEL: str = "low"                        # "none" | "low" | "medium" | "high"

# ---------------------------------------------------------------------------
# Paths  (override via environment variables or edit here)
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
IMAGE_FOLDER: Path = Path(os.environ.get("IMAGE_FOLDER", BASE_DIR / "images"))
OUTPUT_FOLDER: Path = Path(os.environ.get("OUTPUT_FOLDER", BASE_DIR / "output"))

# ---------------------------------------------------------------------------
# IIIF downloader defaults
# ---------------------------------------------------------------------------

BOOK_ID: str = "bsb11005578"
IIIF_MANIFEST_URL: str = (
    f"https://api.digitale-sammlungen.de/iiif/presentation/v2/{BOOK_ID}/manifest"
)
DOWNLOAD_START_SEQ: int = 15   # first canvas to download (1-based, inclusive)
DOWNLOAD_END_SEQ: int = 102    # last canvas to download (1-based, inclusive)
DOWNLOAD_DELAY_SECONDS: float = 0.5

# ---------------------------------------------------------------------------
# Entity types  (German environmental / historical focus)
# ---------------------------------------------------------------------------

ENTITY_TYPES: dict[str, str] = {
    "Animal": (
        "Tier, Tiergruppe oder Tierart (z. B. Wolf, Forelle, Rinderherde)"
    ),
    "Artefact": (
        "Menschengemachtes, unbelebtes Artefakt (z. B. Brücke, Mühle, Eisenbahn)"
    ),
    "Environment": (
        "Biotop/Habitat, natürliche Umgebung, kein Eigenname einer Stadt/Ort "
        "(z. B. Wald, Uferzone, Auenlandschaft)"
    ),
    "Environmental Impact": (
        "Umweltauswirkung/Effekt (z. B. Überschwemmung, Erosion, Abholzung)"
    ),
    "Person": (
        "NUR einzelne, namentlich identifizierbare historische Persönlichkeiten "
        "mit Eigennamen (z. B. Kaiser Karl IV., Herzog Ernst, Fürst Reuß). "
        "KEINE Berufsgruppen, Bevölkerungsgruppen, Völker oder generische Bezeichnungen."
    ),
    "Location": (
        "NUR eindeutig identifizierbare, konkrete geographische Orte mit Eigennamen: "
        "Länder, Regionen, Städte, Dörfer (z. B. Weimar, Thüringen, Böhmen, Sachsen). "
        "KEINE abstrakten Gebietsbezeichnungen."
    ),
    "Organisation": (
        "Organisation/Verband/Institution (z. B. Universität Jena, Forstamt Saalfeld, "
        "Kloster Ettal)"
    ),
    "Natural Object": (
        "Natürlich vorkommendes Objekt ohne Veränderung durch menschliches Zutun "
        "(z. B. Donau, Fichtelgebirge, Lech, Brocken)"
    ),
    "Plant": "Pflanze/Pflanzenart (z. B. Eiche, Buche, Weizen)",
    "Resource": (
        "Natürlich vorkommende Ressource (z. B. Holz, Erz, Kohle, Quellwasser)"
    ),
    "Climate": (
        "Klima-/Wetter-/Temperatur-Phänomen (z. B. Frost, Dürre, Schneesturm, Regen)"
    ),
}

# ---------------------------------------------------------------------------
# Entity colours for the HTML viewer
# ---------------------------------------------------------------------------

ENTITY_COLORS: dict[str, str] = {
    "Animal":               "#c62828",
    "Artefact":             "#e65100",
    "Environment":          "#2e7d32",
    "Environmental Impact": "#bf360c",
    "Person":               "#6a1b9a",
    "Location":             "#1565c0",
    "Organisation":         "#37474f",
    "Natural Object":       "#5d4037",
    "Plant":                "#558b2f",
    "Resource":             "#f9a825",
    "Climate":              "#546e7a",
}

ENTITY_LABELS: dict[str, str] = {
    "Animal":               "Tiere",
    "Artefact":             "Artefakte",
    "Environment":          "Umgebung",
    "Environmental Impact": "Umwelteinflüsse",
    "Person":               "Personen",
    "Location":             "Orte",
    "Organisation":         "Organisationen",
    "Natural Object":       "Naturobjekte",
    "Plant":                "Pflanzen",
    "Resource":             "Ressourcen",
    "Climate":              "Klima",
}
