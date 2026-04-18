import flet as ft
from components.dialog_helper import show_confirm_dialog


def confirm_delete_dialog(page: ft.Page, title: str, message: str, on_confirm):
    """Diálogo de confirmación antes de eliminar un registro."""
    show_confirm_dialog(
        page, title, message, on_confirm,
        confirm_text="Eliminar",
        icon=ft.Icons.WARNING_AMBER_ROUNDED,
    )
