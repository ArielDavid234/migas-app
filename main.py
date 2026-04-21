import traceback
import flet as ft
from database.db import init_db, get_session
from database.seed import run_seed
from database.models import User, UserRole, ClockRecord
from auth.login import login_view
from auth.clock import clock_view
from views.dashboard import dashboard_view
from views.cuenta import cuenta_view
from views.inventario import inventario_view
from views.horario import horario_view
from views.reportes import reportes_view
from views.pedidos import pedidos_view
from views.cafeteria import cafeteria_view
from views.rentas import rentas_view
from views.servicios import servicios_view
from views.delivery import delivery_view
from views.empleados import empleados_view
from views.backup_view import backup_view
from components.sidebar import sidebar, sidebar_drawer
from assets.styles import FONT_FAMILY, ERROR, PRIMARY_DARK, SUBTITLE_SIZE, BODY_SIZE
from utils.responsive import is_mobile, is_phone, get_device, r_sidebar_width, r_dialog_width, PHONE
from utils.toast import show_toast
from utils.alerts import get_inventory_alert_count, get_pending_orders_count, get_unpaid_services_count, get_schedule_notification_count
from utils.backup import create_backup
from components.dialog_helper import show_confirm_dialog
from utils.audit import log_action


def main(page: ft.Page):
    page.title = "MigasApp — Gestión de Gasolinera"
    page.theme_mode = ft.ThemeMode.LIGHT

    # Light theme — colores primarios del app
    _light_scheme = ft.ColorScheme(
        primary="#1565C0",
        on_primary="#FFFFFF",
        primary_container="#BBDEFB",
        on_primary_container="#0D47A1",
        secondary="#FF6F00",
        on_secondary="#FFFFFF",
        error="#D32F2F",
        on_error="#FFFFFF",
        surface="#F5F5F5",           # Fondo de la página (gris suave)
        on_surface="#212121",        # Texto principal
        on_surface_variant="#757575",# Texto secundario
        outline_variant="#E0E0E0",   # Divisores / bordes sutiles
        surface_container="#FFFFFF", # Cards / paneles (blanco sobre gris)
        surface_container_low="#FAFAFA",
        surface_container_high="#EEEEEE",
        surface_container_highest="#E0E0E0",
    )
    # Dark theme — mismo diseño, colores oscuros
    _dark_scheme = ft.ColorScheme(
        primary="#90CAF9",
        on_primary="#0D47A1",
        primary_container="#1565C0",
        on_primary_container="#BBDEFB",
        secondary="#FFCA28",
        on_secondary="#212121",
        error="#EF9A9A",
        on_error="#B71C1C",
        surface="#121212",           # Fondo de la página (más oscuro)
        on_surface="#E0E0E0",        # Texto principal
        on_surface_variant="#9E9E9E",# Texto secundario
        outline_variant="#3A3A3A",   # Divisores / bordes sutiles
        surface_container="#1E1E1E", # Cards / paneles (ligeramente más claro)
        surface_container_low="#181818",
        surface_container_high="#252525",
        surface_container_highest="#2E2E2E",
    )
    page.theme = ft.Theme(font_family=FONT_FAMILY, color_scheme=_light_scheme)
    page.dark_theme = ft.Theme(font_family=FONT_FAMILY, color_scheme=_dark_scheme)
    page.bgcolor = ft.Colors.SURFACE  # Sigue el tema activo (más oscuro que cards)

    # Window settings only for desktop
    if not is_mobile(page):
        page.window.width = 1200
        page.window.height = 750
        page.window.min_width = 900
        page.window.min_height = 600
        page.fonts = {"Segoe UI": "Segoe UI"}

    # State
    current_user: User | None = None
    _rebuild_layout_fn = [None]  # Mutable ref to rebuild layout after theme change
    _current_route = ["dashboard"]  # Track active route for theme-switch rebuild

    def toggle_theme():
        """Switch between light and dark theme, then rebuild everything."""
        page.theme_mode = (
            ft.ThemeMode.LIGHT
            if page.theme_mode == ft.ThemeMode.DARK
            else ft.ThemeMode.DARK
        )
        if _rebuild_layout_fn[0]:
            _rebuild_layout_fn[0](_current_route[0])
        else:
            page.update()

    def show_login():
        nonlocal current_user
        current_user = None
        page.controls.clear()
        page.add(login_view(page, on_login_success=on_login_success))
        page.update()

    def on_login_success(user: User):
        nonlocal current_user
        current_user = user
        log_action(user.id, "LOGIN", "User", user.id, f"{user.name} inició sesión")

        # Workers must clock in first
        if user.role == UserRole.WORKER:
            session = get_session()
            try:
                active = session.query(ClockRecord).filter_by(
                    user_id=user.id, clock_out=None
                ).first()
                if active:
                    show_main_app(user)
                else:
                    show_clock_screen(user)
            finally:
                session.close()
        else:
            # Admin goes directly to dashboard
            show_main_app(user)

    def show_clock_screen(user: User):
        page.controls.clear()
        page.add(
            clock_view(
                page,
                user,
                on_clock_in=lambda: show_main_app(user),
                on_clock_out=lambda: show_login(),
            )
        )
        page.update()

    def show_main_app(user: User):
        nonlocal current_user
        current_user = user

        current_route = "dashboard"
        content_area = ft.Column(expand=True)

        def _get_alert_counts() -> dict:
            """Compute badge counts for sidebar items."""
            try:
                counts = {
                    "inventario": get_inventory_alert_count(),
                    "pedidos": get_pending_orders_count(),
                    "servicios": get_unpaid_services_count(),
                }
                if user.role.value == "worker":
                    counts["horario"] = get_schedule_notification_count(user.id)
                return counts
            except Exception:
                return {}

        def _do_backup():
            """Manual backup triggered from sidebar."""
            try:
                path = create_backup(label="manual")
                log_action(user.id if user else None, "BACKUP", "Database", details="Backup manual")
                show_toast(page, f"Backup creado exitosamente", is_success=True)
            except Exception as exc:
                show_toast(page, f"Error al crear backup: {exc}", is_error=True)

        def on_navigate(route: str):
            nonlocal current_route
            current_route = route
            _current_route[0] = route  # keep ref for theme-switch rebuild
            content_area.controls.clear()

            # Show loading indicator
            content_area.controls.append(
                ft.Container(
                    content=ft.Column(
                        [ft.ProgressRing(), ft.Text("Cargando…", color="#757575")],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=12,
                    ),
                    alignment=ft.Alignment(0, 0),
                    expand=True,
                )
            )
            page.update()

            # Load the view with error handling
            content_area.controls.clear()
            if route in view_map:
                try:
                    content_area.controls.append(view_map[route]())
                except Exception as exc:
                    traceback.print_exc()
                    content_area.controls.append(
                        ft.Container(
                            content=ft.Column(
                                [
                                    ft.Icon(ft.Icons.ERROR_OUTLINE, size=60, color=ERROR),
                                    ft.Text(
                                        "Error al cargar el módulo",
                                        size=20,
                                        weight=ft.FontWeight.BOLD,
                                        color="#424242",
                                    ),
                                    ft.Text(
                                        str(exc),
                                        size=14,
                                        color="#757575",
                                        text_align=ft.TextAlign.CENTER,
                                    ),
                                    ft.ElevatedButton(
                                        "Reintentar",
                                        icon=ft.Icons.REFRESH,
                                        on_click=lambda e, r=route: on_navigate(r),
                                    ),
                                ],
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                alignment=ft.MainAxisAlignment.CENTER,
                                spacing=10,
                            ),
                            alignment=ft.Alignment(0, 0),
                            expand=True,
                        )
                    )
                    show_toast(page, f"Error: {exc}", is_error=True)
            else:
                content_area.controls.append(
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Icon(ft.Icons.CONSTRUCTION, size=60, color=ft.Colors.OUTLINE_VARIANT),
                                ft.Text(
                                    f"Módulo: {route.replace('_', ' ').title()}",
                                    size=24,
                                    weight=ft.FontWeight.BOLD,
                                    color=ft.Colors.ON_SURFACE,
                                ),
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            alignment=ft.MainAxisAlignment.CENTER,
                            spacing=10,
                        ),
                        alignment=ft.Alignment(0, 0),
                        expand=True,
                    )
                )
            # Close drawer after navigation on mobile
            if is_phone(page) and page.drawer:
                page.drawer.open = False
            page.update()

        def on_logout():
            """Show confirmation dialog before logging out."""
            def _do_logout():
                log_action(user.id, "LOGOUT", "User", user.id, f"{user.name} cerró sesión")
                if user.role == UserRole.WORKER:
                    show_clock_screen(user)
                else:
                    show_login()

            show_confirm_dialog(
                page,
                "Cerrar Sesión",
                "¿Estás seguro de que deseas cerrar sesión?",
                _do_logout,
                confirm_text="Cerrar Sesión",
                icon=ft.Icons.LOGOUT,
            )

        view_map = {
            "dashboard": lambda: dashboard_view(page, user, on_navigate=on_navigate),
            "cuenta": lambda: cuenta_view(page, user),
            "inventario": lambda: inventario_view(page, user),
            "horario": lambda: horario_view(page, user),
            "reportes": lambda: reportes_view(page, user),
            "pedidos": lambda: pedidos_view(page, user),
            "cafeteria": lambda: cafeteria_view(page, user),
            "rentas": lambda: rentas_view(page, user),
            "servicios": lambda: servicios_view(page, user),
            "delivery": lambda: delivery_view(page, user),
            "empleados": lambda: empleados_view(page, user),
            "backup": lambda: backup_view(page, user),
        }

        # Load initial view
        try:
            content_area.controls.append(view_map["dashboard"]())
        except Exception as exc:
            traceback.print_exc()
            show_toast(page, f"Error al cargar Dashboard: {exc}", is_error=True)

        def _build_layout(route: str = "dashboard"):
            """Build layout appropriate for current screen size, optionally reloading a route."""
            device = get_device(page)
            # Rebuild content area with the current route so colors refresh
            content_area.controls.clear()
            try:
                content_area.controls.append(view_map.get(route, view_map["dashboard"])()
                )
            except Exception:
                traceback.print_exc()
            page.controls.clear()
            counts = _get_alert_counts()

            if device == PHONE:
                # Phone: drawer navigation + hamburger menu
                drawer = sidebar_drawer(page, user, on_navigate, on_logout, on_toggle_theme=toggle_theme)
                page.drawer = drawer

                def _open_drawer(e):
                    page.drawer.open = True
                    page.update()

                page.appbar = ft.AppBar(
                    leading=ft.IconButton(ft.Icons.MENU, on_click=_open_drawer, icon_color="white"),
                    title=ft.Text("MigasApp", color="white", size=18, weight=ft.FontWeight.BOLD),
                    bgcolor="#0D47A1",
                    center_title=True,
                )
                page.add(ft.Container(content=content_area, expand=True, padding=8))
            else:
                # Tablet & Desktop: sidebar layout (narrower on tablet)
                page.appbar = None
                page.drawer = None
                sw = r_sidebar_width(page)
                layout = ft.Row(
                    [
                        sidebar(page, user, on_navigate, on_logout, on_toggle_theme=toggle_theme,
                               on_backup=_do_backup, alert_counts=counts, active_route=route, width=sw),
                        ft.VerticalDivider(width=1, color=ft.Colors.OUTLINE_VARIANT),
                        ft.Container(content=content_area, expand=True),
                    ],
                    expand=True,
                    spacing=0,
                )
                page.add(layout)

            page.update()

        _rebuild_layout_fn[0] = _build_layout

        # Track last device type and calendar-visibility threshold to avoid unnecessary rebuilds
        last_device = [get_device(page)]
        _CALENDAR_THRESHOLD = 950
        last_show_cal = [(page.width or 1200) >= _CALENDAR_THRESHOLD]

        def _on_resize(e):
            device = get_device(page)
            show_cal = (page.width or 1200) >= _CALENDAR_THRESHOLD
            if device != last_device[0] or show_cal != last_show_cal[0]:
                last_device[0] = device
                last_show_cal[0] = show_cal
                _build_layout(_current_route[0])

        page.on_resized = _on_resize
        _build_layout()

    # Initialize DB, auto-backup, and show login
    run_seed()
    try:
        create_backup(label="auto")
    except Exception:
        pass  # Don't block startup if backup fails
    show_login()


if __name__ == "__main__":
    ft.run(main)
