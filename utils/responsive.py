"""Responsive helpers for all screen sizes."""
import flet as ft

# ── Breakpoints ──────────────────────────────────────────────
PHONE_MAX = 600
TABLET_MAX = 1024

# Device types
PHONE = "phone"
TABLET = "tablet"
DESKTOP = "desktop"


def _get_width(page: ft.Page) -> float:
    """Get effective page width."""
    try:
        w = page.width or page.window.width
        if w and w > 0:
            return w
    except Exception:
        pass
    return 1200  # safe fallback


def get_device(page: ft.Page) -> str:
    """Return device type: 'phone', 'tablet', or 'desktop'."""
    platform = getattr(page, "platform", None)
    if platform in (ft.PagePlatform.IOS, ft.PagePlatform.ANDROID):
        w = _get_width(page)
        return PHONE if w < PHONE_MAX else TABLET
    w = _get_width(page)
    if w < PHONE_MAX:
        return PHONE
    if w < TABLET_MAX:
        return TABLET
    return DESKTOP


def is_mobile(page: ft.Page) -> bool:
    """True for phone or tablet."""
    return get_device(page) in (PHONE, TABLET)


def is_phone(page: ft.Page) -> bool:
    return get_device(page) == PHONE


def is_tablet(page: ft.Page) -> bool:
    return get_device(page) == TABLET


def is_desktop(page: ft.Page) -> bool:
    return get_device(page) == DESKTOP


# ── Responsive values ────────────────────────────────────────
def r_val(page: ft.Page, phone, tablet, desktop):
    """Return value based on device type."""
    d = get_device(page)
    if d == PHONE:
        return phone
    if d == TABLET:
        return tablet
    return desktop


def r_padding(page: ft.Page):
    """Responsive outer padding."""
    return r_val(page, 8, 16, 24)


def r_spacing(page: ft.Page):
    """Responsive general spacing."""
    return r_val(page, 8, 12, 16)


def r_font_title(page: ft.Page):
    return r_val(page, 20, 24, 28)


def r_font_subtitle(page: ft.Page):
    return r_val(page, 16, 18, 20)


def r_font_body(page: ft.Page):
    return r_val(page, 13, 14, 14)


def r_font_small(page: ft.Page):
    return r_val(page, 11, 12, 12)


def r_icon(page: ft.Page, base=20):
    """Scale icon size."""
    return r_val(page, max(14, base - 4), base, base)


def r_dialog_width(page: ft.Page, desktop_width=450):
    """Responsive dialog width. On phone uses ~90% of screen."""
    d = get_device(page)
    if d == PHONE:
        w = _get_width(page)
        return min(desktop_width, w * 0.92)
    if d == TABLET:
        return min(desktop_width, 500)
    return desktop_width


def r_field_width(page: ft.Page, desktop_width=200):
    """Responsive text field width."""
    d = get_device(page)
    if d == PHONE:
        return None  # expand to fill
    if d == TABLET:
        return min(desktop_width, 280)
    return desktop_width


def r_sidebar_width(page: ft.Page):
    """Sidebar width: hidden on phone, narrow on tablet, full on desktop."""
    return r_val(page, 0, 200, 240)


def r_calendar_width(page: ft.Page):
    """Calendar panel width."""
    return r_val(page, None, 260, 300)


def r_side_panel_width(page: ft.Page):
    """Right side panel width (alerts, calendar, etc.)."""
    return r_val(page, None, 280, 320)


# Ancho mínimo de ventana para mostrar el panel lateral junto al contenido.
# Sidebar (~240px) + panel (~300px) + contenido mínimo + padding ≈ 950px
_SIDE_PANEL_MIN_WIDTH = 950

# ── Layout helpers ───────────────────────────────────────────
def responsive_layout(page: ft.Page, main_content, side_panel, side_width=320):
    """Return Row (desktop/tablet) or stacked Column (phone/narrow window) layout."""
    d = get_device(page)
    page_w = _get_width(page)
    # En teléfono O cuando la ventana es muy angosta, apilar verticalmente
    if d == PHONE or page_w < _SIDE_PANEL_MIN_WIDTH:
        return ft.Column([
            main_content,
            side_panel,
        ], expand=True, scroll=ft.ScrollMode.AUTO)
    else:
        sw = r_side_panel_width(page) or side_width
        return ft.Row([
            ft.Container(content=main_content, expand=True, padding=ft.padding.only(right=12 if d == TABLET else 16)),
            ft.Column([side_panel], width=sw),
        ], spacing=0, expand=True, vertical_alignment=ft.CrossAxisAlignment.START)


def responsive_row(page: ft.Page, controls, spacing=16):
    """Row that wraps on phone, normal row on tablet/desktop."""
    d = get_device(page)
    if d == PHONE:
        return ft.Column(controls, spacing=spacing)
    return ft.Row(controls, spacing=spacing, wrap=True)


def scrollable_row(controls, **kwargs):
    """Horizontally scrollable row for tables/wide content on small screens."""
    return ft.Row(controls, scroll=ft.ScrollMode.AUTO, **kwargs)
