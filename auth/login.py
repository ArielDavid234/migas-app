import flet as ft
import hashlib
from database.db import get_session
from database.models import User
from config import APP_SALT
from assets.styles import (
    PRIMARY, PRIMARY_DARK, SURFACE, ERROR, TEXT_PRIMARY,
    TEXT_SECONDARY, FONT_FAMILY, TITLE_SIZE, BODY_SIZE,
)
from utils.responsive import is_phone, r_val


def hash_password(password: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), APP_SALT.encode(), 100_000
    ).hex()


def login_view(page: ft.Page, on_login_success):
    """Pantalla de login. Llama on_login_success(user) cuando el login es exitoso."""
    phone = is_phone(page)
    field_w = None if phone else 300
    card_w = None if phone else 400
    card_pad = 24 if phone else 40
    icon_sz = r_val(page, 44, 50, 60)
    title_sz = r_val(page, 22, 26, TITLE_SIZE)

    username_field = ft.TextField(
        label="Usuario",
        width=field_w,
        expand=phone,
        border_color=PRIMARY,
        focused_border_color=PRIMARY_DARK,
        prefix_icon=ft.Icons.PERSON,
        text_size=BODY_SIZE,
    )

    password_field = ft.TextField(
        label="Contraseña",
        width=field_w,
        expand=phone,
        password=True,
        can_reveal_password=True,
        border_color=PRIMARY,
        focused_border_color=PRIMARY_DARK,
        prefix_icon=ft.Icons.LOCK,
        text_size=BODY_SIZE,
    )

    error_text = ft.Text("", color=ERROR, size=BODY_SIZE)

    def do_login(e):
        username = username_field.value.strip()
        password = password_field.value.strip()

        if not username or not password:
            error_text.value = "Completa todos los campos"
            page.update()
            return

        session = get_session()
        try:
            user = session.query(User).filter_by(
                username=username,
                password_hash=hash_password(password),
                is_active=True,
            ).first()

            if user:
                error_text.value = ""
                on_login_success(user)
            else:
                error_text.value = "Usuario o contraseña incorrectos"
                page.update()
        finally:
            session.close()

    def on_key_enter(e):
        if e.key == "Enter":
            do_login(e)

    password_field.on_submit = do_login

    login_button = ft.ElevatedButton(
        content=ft.Text("Iniciar Sesión", color="white", size=15, weight=ft.FontWeight.W_500),
        width=field_w,
        expand=phone,
        height=45,
        bgcolor=PRIMARY,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
        on_click=do_login,
    )

    login_card = ft.Container(
        content=ft.Column(
            [
                ft.Icon(ft.Icons.LOCAL_GAS_STATION, size=icon_sz, color=PRIMARY),
                ft.Text(
                    "MigasApp",
                    size=title_sz,
                    weight=ft.FontWeight.BOLD,
                    color=PRIMARY_DARK,
                    font_family=FONT_FAMILY,
                ),
                ft.Text(
                    "Gestión de Gasolinera",
                    size=BODY_SIZE,
                    color=TEXT_SECONDARY,
                ),
                ft.Divider(height=20, color="transparent"),
                username_field,
                password_field,
                error_text,
                ft.Divider(height=10, color="transparent"),
                login_button,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
        ),
        width=card_w,
        expand=phone,
        padding=card_pad,
        border_radius=16,
        bgcolor=SURFACE,
        shadow=ft.BoxShadow(
            spread_radius=1,
            blur_radius=15,
            color=ft.Colors.with_opacity(0.2, "black"),
            offset=ft.Offset(0, 4),
        ),
    )

    return ft.Container(
        content=login_card,
        alignment=ft.Alignment(0, 0),
        expand=True,
        bgcolor="#E3F2FD",
    )
