# Tema y estilos de la aplicación
import flet as ft

# Colores de marca — fijos, no cambian con el tema
PRIMARY = "#1565C0"       # Azul fuerte
PRIMARY_LIGHT = "#1E88E5"
PRIMARY_DARK = "#0D47A1"
ACCENT = "#FF6F00"        # Naranja/ámbar
ERROR = "#D32F2F"
SUCCESS = "#2E7D32"
SIDEBAR_BG = "#0D47A1"
SIDEBAR_TEXT = "#FFFFFF"

# Colores semánticos — se resuelven dinámicamente según el tema activo (claro u oscuro)
# Flet los pasa al motor Flutter que aplica el ColorScheme configurado en page.theme
BACKGROUND = ft.Colors.SURFACE          # Fondo de la página
SURFACE = ft.Colors.SURFACE_CONTAINER   # Cards, paneles, diálogos
TEXT_PRIMARY = ft.Colors.ON_SURFACE     # Texto principal
TEXT_SECONDARY = ft.Colors.ON_SURFACE_VARIANT  # Texto secundario / placeholder
DIVIDER_COLOR = ft.Colors.OUTLINE_VARIANT      # Divisores y bordes sutiles

# Fuentes
import sys as _sys
FONT_FAMILY = "Segoe UI" if _sys.platform == "win32" else "Helvetica Neue"
TITLE_SIZE = 28
SUBTITLE_SIZE = 20
BODY_SIZE = 14
SMALL_SIZE = 12
