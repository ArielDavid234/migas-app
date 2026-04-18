import os
import sys


def _get_data_dir():
    """Return a writable directory for app data, works on desktop and iOS."""
    if sys.platform == "darwin":
        # iOS / macOS sandbox — use Application Support
        support = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "MigasApp")
        os.makedirs(support, exist_ok=True)
        return support
    # Windows / Linux — same folder as the script
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = _get_data_dir()
DB_PATH = os.path.join(DATA_DIR, "migasapp.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

APP_NAME = "MigasApp"
GAS_STATION_NAME = "Gasolinera Migas"
APP_SALT = "m1g4s_4pp_s4lt_2024"

HOURLY_RATE = 15.0  # Dólares por hora

# Categorías de inventario predefinidas
DEFAULT_CATEGORIES = [
    "Cigarros", "Vapes", "Coca Cola", "Zuma", "Pepsi",
    "Eagle Brands", "Gold Coast", "Agua", "Helados", "FritoLay",
    "Aceites para carros", "Misceláneas", "Maní", "Redbull",
    "Chicharrones y demás", "Arizona",
    "Gabo gafas y gorras (consignación)",
    "Faro Bakery", "Olores para carros", "Hielo",
    "Gas Propano", "Viagaras", "Medicinas", "Pullover",
    "Cargadores de Elisa",
]

# Días antes del vencimiento para alertar
EXPIRY_ALERT_DAYS = 7
# Umbral mínimo de stock para alertar
LOW_STOCK_THRESHOLD = 2

# Marcas de cigarros para reportes
DEFAULT_CIGARETTE_BRANDS = [
    "Marlboro Red", "Marlboro Gold", "Marlboro Menthol",
    "Camel", "Camel Blue", "Newport", "Newport Menthol",
    "Pall Mall", "L&M", "Winston",
    "American Spirit", "Kool", "Parliament",
    "Lucky Strike", "Maverick",
]

# Nombres de Scratch (Lottery) para reportes
DEFAULT_SCRATCH_NAMES = [
    "$1 Scratch", "$2 Scratch", "$3 Scratch",
    "$5 Scratch", "$10 Scratch", "$20 Scratch",
    "$30 Scratch", "$50 Scratch",
]

# Ítems especiales para reportes diarios
DEFAULT_SPECIAL_ITEMS = [
    "Gas propano", "Gafas de 12", "Gafas de 12.99", "Viagara",
    "Enguatadas", "Sombrero grande", "Sombrero pequeño", "Gorras", "Cargadores",
]
