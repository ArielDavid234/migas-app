"""Centralized dialog helpers — reusable confirm, info, and form dialogs."""

import flet as ft
from assets.styles import PRIMARY_DARK, ERROR, SUCCESS, SUBTITLE_SIZE, BODY_SIZE


def show_confirm_dialog(
    page: ft.Page,
    title: str,
    message: str,
    on_confirm,
    confirm_text: str = "Confirmar",
    confirm_color: str = ERROR,
    icon: str = ft.Icons.WARNING_AMBER_ROUNDED,
    icon_color: str | None = None,
):
    """General-purpose confirmation dialog."""

    def _yes(e):
        page.pop_dialog()
        on_confirm()

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Row([
            ft.Icon(icon, color=icon_color or confirm_color, size=24),
            ft.Text(title, size=SUBTITLE_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
        ], spacing=8),
        content=ft.Text(message, size=BODY_SIZE),
        actions=[
            ft.TextButton(content=ft.Text("Cancelar"), on_click=lambda e: page.pop_dialog()),
            ft.ElevatedButton(
                content=ft.Text(confirm_text, color="white"),
                bgcolor=confirm_color,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                on_click=_yes,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dlg)


def show_info_dialog(page: ft.Page, title: str, message: str, icon: str = ft.Icons.INFO_OUTLINE):
    """Simple informational dialog with an OK button."""
    dlg = ft.AlertDialog(
        modal=False,
        title=ft.Row([
            ft.Icon(icon, color=PRIMARY_DARK, size=24),
            ft.Text(title, size=SUBTITLE_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
        ], spacing=8),
        content=ft.Text(message, size=BODY_SIZE),
        actions=[
            ft.ElevatedButton(
                content=ft.Text("OK", color="white"),
                bgcolor=PRIMARY_DARK,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                on_click=lambda e: page.pop_dialog(),
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dlg)


def show_form_dialog(
    page: ft.Page,
    title: str,
    content: ft.Control,
    on_save,
    save_text: str = "Guardar",
    save_color: str = SUCCESS,
    icon: str = ft.Icons.EDIT_NOTE,
    width: int | None = None,
):
    """Dialog wrapping custom form content with Save/Cancel buttons."""

    def _save(e):
        page.pop_dialog()
        on_save()

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Row([
            ft.Icon(icon, color=PRIMARY_DARK, size=24),
            ft.Text(title, size=SUBTITLE_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
        ], spacing=8),
        content=ft.Container(content=content, width=width),
        actions=[
            ft.TextButton(content=ft.Text("Cancelar"), on_click=lambda e: page.pop_dialog()),
            ft.ElevatedButton(
                content=ft.Text(save_text, color="white"),
                bgcolor=save_color,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                on_click=_save,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dlg)
