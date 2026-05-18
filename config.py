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

APP_NAME = "MiGas App"
APP_LOGO_ASSET = "LOGO.jpg"
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

# ── OCR.space API (gratis, funciona en iOS/macOS/Windows) ──
# https://ocr.space/ocrapi/freekey
OCR_SPACE_API_KEY = "K84112862188957"

# ── Loyalty / Recompensas (Cafetería) ──
# Compras necesarias para desbloquear una recompensa
LOYALTY_PURCHASES_FOR_REWARD = 10

# ── Mapeo de categorías para Ventas por Departamento (DEPARTMENT REPORT) ──
# Ajusta las palabras clave según los nombres que usa tu caja registradora.
# Cada categoría agrupa los departamentos cuya DESCRIPCIÓN contenga alguna de esas palabras.
DEPT_CATEGORIES = {
    "Gasolina": [
        # English
        "gas", "gasoline", "fuel", "unleaded", "diesel", "premium", "regular",
        "super", "petrol", "e85", "ethanol", "octane", "gallon", "pump",
        # Spanish
        "gasolina", "combustible", "gasoil", "sin plomo",
    ],
    "Cafetería": [
        # English — food
        "cafe", "cafeteria", "food", "deli", "hot food", "cold food", "grill",
        "bakery", "pastry", "pizza", "sandwich", "hotdog", "hot dog",
        "breakfast", "lunch", "combo", "prepared", "kitchen", "grocery",
        "general", "packaged", "merchandise", "tobacco", "cigarette", "cigar",
        "vape", "candy", "chips", "snack",
        # English — beverages
        "drink", "beverage", "coffee", "soda", "fountain", "juice", "water",
        "beer", "wine", "milk", "energy",
        # Spanish — food
        "comida", "cocina", "panaderia", "panadería", "reposteria",
        "almuerzo", "desayuno", "merienda", "botana", "frituras",
        # Spanish — beverages
        "bebida", "agua", "cerveza", "jugo", "refresco", "leche",
        # Spanish — store items
        "tabaco", "cigarro", "cigarrillo", "dulce", "comestible",
        "abarrote", "tienda", "mercancia", "mercancía",
    ],
    "Rentas": [
        # English
        "rent", "rental", "lease", "sublease", "atm", "space", "machine rental",
        # Spanish
        "renta", "arrendamiento", "alquiler", "maquina", "máquina",
    ],
    "Servicios": [
        # English
        "service", "car wash", "wash", "air", "propane", "phone card",
        "phone", "utility", "utilities", "lottery", "money order",
        "wire transfer", "western union", "western",
        # Spanish
        "servicio", "lavado", "propano", "tarjeta", "loteria", "lotería",
        "giro", "transferencia", "aire", "orden de dinero",
    ],
    "Delivery": [
        # English
        "delivery", "deliver", "online", "doordash", "grubhub",
        "uber eats", "ubereats", "pickup", "pick up", "order", "third party",
        # Spanish
        "entrega", "domicilio", "pedido", "en linea", "en línea",
    ],
}

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
