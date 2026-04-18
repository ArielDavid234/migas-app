"""Reusable toast / snackbar helper for any view."""
import flet as ft

_ERROR_BG = "#D32F2F"
_SUCCESS_BG = "#2E7D32"
_DEFAULT_BG = "#323232"


def show_toast(page: ft.Page, msg: str, is_error: bool = False, is_success: bool = False):
    """Show a brief toast notification at the bottom of the screen."""
    if is_error:
        bg = _ERROR_BG
    elif is_success:
        bg = _SUCCESS_BG
    else:
        bg = _DEFAULT_BG

    page.snack_bar = ft.SnackBar(
        content=ft.Text(msg, color="white"),
        bgcolor=bg,
        duration=4000,
    )
    page.snack_bar.open = True
    page.update()
