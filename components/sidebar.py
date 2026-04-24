import flet as ft
from database.models import UserRole
from assets.styles import (
    SIDEBAR_BG, SIDEBAR_TEXT, PRIMARY_LIGHT, PRIMARY, ACCENT,
    FONT_FAMILY, BODY_SIZE, SMALL_SIZE, ERROR,
)

ACTIVE_BG = "#1565C0"
HOVER_BG = PRIMARY_LIGHT


def _badge(count: int):
    """Small red badge with count. Returns empty container if 0."""
    if count <= 0:
        return ft.Container()
    return ft.Container(
        content=ft.Text(str(count) if count < 100 else "99+", size=10, color="white",
                        weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
        width=20 if count < 10 else 26,
        height=18,
        border_radius=9,
        bgcolor=ERROR,
        alignment=ft.Alignment(0, 0),
    )


def sidebar(page: ft.Page, user, on_navigate, on_logout, on_toggle_theme=None,
            on_backup=None, alert_counts: dict | None = None, active_route: str = "dashboard", width: int = 240):
    """Panel lateral izquierdo con navegación y estado activo."""
    compact = width < 220

    menu_items = [
        ("Principal", ft.Icons.DASHBOARD, "dashboard"),
        ("Cuenta", ft.Icons.ACCOUNT_BALANCE_WALLET, "cuenta"),
        ("Inventario", ft.Icons.INVENTORY_2, "inventario"),
        ("Horario", ft.Icons.CALENDAR_MONTH, "horario"),
        ("Reportes", ft.Icons.ASSESSMENT, "reportes"),
        ("Pedidos", ft.Icons.SHOPPING_CART, "pedidos"),
        ("Cafetería", ft.Icons.COFFEE, "cafeteria"),
        ("Rentas", ft.Icons.HOME, "rentas"),
        ("Servicios", ft.Icons.WATER_DROP, "servicios"),
        ("Delivery Gasolina", ft.Icons.LOCAL_SHIPPING, "delivery"),
    ]

    if user.role == UserRole.ADMIN:
        menu_items.append(("Salarios", ft.Icons.PAYMENTS, "salarios"))
        menu_items.append(("Empleados", ft.Icons.PEOPLE, "empleados"))
        menu_items.append(("Backups", ft.Icons.BACKUP, "backup"))
    else:
        menu_items.append(("Mi Perfil", ft.Icons.PERSON, "empleados"))

    nav_containers: dict[str, ft.Container] = {}

    def _set_active(route: str):
        for r, container in nav_containers.items():
            if r == route:
                container.bgcolor = ACTIVE_BG
                container.border = ft.border.only(left=ft.BorderSide(3, ACCENT))
            else:
                container.bgcolor = "transparent"
                container.border = None
            container.update()

    def _on_item_click(route: str):
        _set_active(route)
        on_navigate(route)

    badges = alert_counts or {}

    def create_menu_item(label, icon, route):
        is_active = route == active_route
        badge_count = badges.get(route, 0)
        row_children = [
            ft.Icon(icon, color=SIDEBAR_TEXT, size=18 if compact else 20),
            ft.Text(label, color=SIDEBAR_TEXT, size=SMALL_SIZE if compact else BODY_SIZE,
                    font_family=FONT_FAMILY, overflow=ft.TextOverflow.ELLIPSIS, expand=True),
        ]
        if badge_count > 0:
            row_children.append(_badge(badge_count))

        container = ft.Container(
            content=ft.Row(
                row_children,
                spacing=8 if compact else 12,
            ),
            padding=ft.padding.symmetric(horizontal=12 if compact else 16, vertical=10 if compact else 12),
            border_radius=8,
            bgcolor=ACTIVE_BG if is_active else "transparent",
            border=ft.border.only(left=ft.BorderSide(3, ACCENT)) if is_active else None,
            on_click=lambda e, r=route: _on_item_click(r),
            on_hover=lambda e, r=route: _on_hover(e, r),
            ink=True,
        )
        nav_containers[route] = container
        return container

    def _on_hover(e, route):
        if route not in nav_containers:
            return
        c = nav_containers[route]
        is_active = c.bgcolor == ACTIVE_BG
        if not is_active:
            c.bgcolor = HOVER_BG if e.data == "true" else "transparent"
            c.update()

    nav_items = [create_menu_item(label, icon, route) for label, icon, route in menu_items]

    logout_btn = ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.LOGOUT, color=SIDEBAR_TEXT, size=20),
                ft.Text("Cerrar Sesión", color=SIDEBAR_TEXT, size=BODY_SIZE, font_family=FONT_FAMILY),
            ],
            spacing=12,
        ),
        padding=ft.padding.symmetric(horizontal=16, vertical=12),
        border_radius=8,
        on_click=lambda e: on_logout(),
        on_hover=lambda e: _on_logout_hover(e),
        ink=True,
    )

    def _on_logout_hover(e):
        logout_btn.bgcolor = HOVER_BG if e.data == "true" else "transparent"
        logout_btn.update()

    # Theme toggle
    is_dark = page.theme_mode == ft.ThemeMode.DARK
    theme_btn = ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.DARK_MODE if is_dark else ft.Icons.LIGHT_MODE,
                        color=SIDEBAR_TEXT, size=20),
                ft.Text("Modo Claro" if is_dark else "Modo Oscuro",
                        color=SIDEBAR_TEXT, size=BODY_SIZE, font_family=FONT_FAMILY),
            ],
            spacing=12,
        ),
        padding=ft.padding.symmetric(horizontal=16, vertical=12),
        border_radius=8,
        on_click=lambda e: on_toggle_theme() if on_toggle_theme else None,
        on_hover=lambda e: _on_theme_hover(e),
        ink=True,
    )

    def _on_theme_hover(e):
        theme_btn.bgcolor = HOVER_BG if e.data == "true" else "transparent"
        theme_btn.update()

    # Backup button (admin only)
    backup_btn = ft.Container() if user.role != UserRole.ADMIN or not on_backup else ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.BACKUP, color=SIDEBAR_TEXT, size=20),
                ft.Text("Backup DB", color=SIDEBAR_TEXT, size=BODY_SIZE, font_family=FONT_FAMILY),
            ],
            spacing=12,
        ),
        padding=ft.padding.symmetric(horizontal=16, vertical=12),
        border_radius=8,
        on_click=lambda e: on_backup() if on_backup else None,
        on_hover=lambda e: _on_backup_hover(e),
        ink=True,
    )

    def _on_backup_hover(e):
        if hasattr(backup_btn, 'bgcolor'):
            backup_btn.bgcolor = HOVER_BG if e.data == "true" else "transparent"
            backup_btn.update()

    return ft.Container(
        content=ft.Column(
            [
                # Header
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(ft.Icons.LOCAL_GAS_STATION, color=SIDEBAR_TEXT, size=36),
                            ft.Text(
                                "MigasApp",
                                color=SIDEBAR_TEXT,
                                size=20,
                                weight=ft.FontWeight.BOLD,
                                font_family=FONT_FAMILY,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=4,
                    ),
                    padding=ft.padding.symmetric(vertical=20),
                    alignment=ft.Alignment(0, 0),
                ),
                ft.Divider(color=PRIMARY_LIGHT, height=1),
                # User info
                ft.Container(
                    content=ft.Row(
                        [
                            ft.CircleAvatar(
                                content=ft.Text(user.name[0].upper()),
                                bgcolor=PRIMARY_LIGHT,
                                radius=16,
                            ),
                            ft.Column(
                                [
                                    ft.Text(user.name, color=SIDEBAR_TEXT, size=BODY_SIZE, weight=ft.FontWeight.W_500),
                                    ft.Text(
                                        user.role.value.capitalize(),
                                        color=ft.Colors.with_opacity(0.7, SIDEBAR_TEXT),
                                        size=SMALL_SIZE,
                                    ),
                                ],
                                spacing=0,
                            ),
                        ],
                        spacing=10,
                    ),
                    padding=ft.padding.symmetric(horizontal=16, vertical=10),
                ),
                ft.Divider(color=PRIMARY_LIGHT, height=1),
                # Navigation
                ft.Column(
                    nav_items,
                    spacing=2,
                    scroll=ft.ScrollMode.AUTO,
                    expand=True,
                ),
                # Logout
                ft.Divider(color=PRIMARY_LIGHT, height=1),
                theme_btn,
                backup_btn,
                logout_btn,
                ft.Container(height=10),
            ],
            spacing=0,
            expand=True,
        ),
        width=width,
        bgcolor=SIDEBAR_BG,
        border_radius=ft.border_radius.only(top_right=0, bottom_right=0),
    )


def sidebar_drawer(page: ft.Page, user, on_navigate, on_logout, on_toggle_theme=None, active_route: str = "dashboard"):
    """NavigationDrawer version of the sidebar for mobile."""

    menu_items = [
        ("Principal", ft.Icons.DASHBOARD, "dashboard"),
        ("Cuenta", ft.Icons.ACCOUNT_BALANCE_WALLET, "cuenta"),
        ("Inventario", ft.Icons.INVENTORY_2, "inventario"),
        ("Horario", ft.Icons.CALENDAR_MONTH, "horario"),
        ("Reportes", ft.Icons.ASSESSMENT, "reportes"),
        ("Pedidos", ft.Icons.SHOPPING_CART, "pedidos"),
        ("Cafetería", ft.Icons.COFFEE, "cafeteria"),
        ("Rentas", ft.Icons.HOME, "rentas"),
        ("Servicios", ft.Icons.WATER_DROP, "servicios"),
        ("Delivery Gasolina", ft.Icons.LOCAL_SHIPPING, "delivery"),
    ]

    if user.role == UserRole.ADMIN:
        menu_items.append(("Salarios", ft.Icons.PAYMENTS, "salarios"))
        menu_items.append(("Empleados", ft.Icons.PEOPLE, "empleados"))
        menu_items.append(("Backups", ft.Icons.BACKUP, "backup"))
    else:
        menu_items.append(("Mi Perfil", ft.Icons.PERSON, "empleados"))

    destinations = []
    route_index = {}
    for i, (label, icon, route) in enumerate(menu_items):
        destinations.append(ft.NavigationDrawerDestination(
            label=label, icon=icon, selected_icon=icon,
        ))
        route_index[i] = route

    def _on_change(e):
        idx = e.control.selected_index
        if idx is not None and idx in route_index:
            on_navigate(route_index[idx])

    header = ft.Container(
        content=ft.Column([
            ft.Icon(ft.Icons.LOCAL_GAS_STATION, color=SIDEBAR_TEXT, size=36),
            ft.Text("MigasApp", color=SIDEBAR_TEXT, size=20, weight=ft.FontWeight.BOLD),
            ft.Text(f"{user.name} ({user.role.value.capitalize()})",
                    color=ft.Colors.with_opacity(0.7, SIDEBAR_TEXT), size=SMALL_SIZE),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
        padding=ft.padding.symmetric(vertical=20, horizontal=16),
        bgcolor=SIDEBAR_BG,
    )

    is_dark_drawer = page.theme_mode == ft.ThemeMode.DARK
    theme_tile = ft.NavigationDrawerDestination(
        label="Modo Claro" if is_dark_drawer else "Modo Oscuro",
        icon=ft.Icons.DARK_MODE if is_dark_drawer else ft.Icons.LIGHT_MODE,
        selected_icon=ft.Icons.DARK_MODE if is_dark_drawer else ft.Icons.LIGHT_MODE,
    )

    logout_tile = ft.NavigationDrawerDestination(
        label="Cerrar Sesión", icon=ft.Icons.LOGOUT, selected_icon=ft.Icons.LOGOUT,
    )

    drawer = ft.NavigationDrawer(
        controls=[
            header,
            ft.Divider(height=1),
            *destinations,
            ft.Divider(height=1),
            theme_tile,
            logout_tile,
        ],
        on_change=_on_change,
        selected_index=0,
    )

    # Intercept theme + logout indices
    theme_idx = len(destinations)
    logout_idx = len(destinations) + 1
    original_on_change = _on_change

    def _on_change_with_logout(e):
        idx = e.control.selected_index
        if idx == theme_idx:
            if on_toggle_theme:
                on_toggle_theme()
        elif idx == logout_idx:
            on_logout()
        elif idx is not None and idx in route_index:
            on_navigate(route_index[idx])

    drawer.on_change = _on_change_with_logout

    return drawer
