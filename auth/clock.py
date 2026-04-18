import flet as ft
from datetime import datetime
from database.db import get_session
from database.models import User, ClockRecord
from assets.styles import (
    PRIMARY, PRIMARY_DARK, SURFACE, ERROR, SUCCESS,
    TEXT_SECONDARY, FONT_FAMILY, TITLE_SIZE, SUBTITLE_SIZE, BODY_SIZE,
)
from utils.responsive import is_phone, r_val


def clock_view(page: ft.Page, user: User, on_clock_in, on_clock_out):
    """
    Pantalla de Clock In / Clock Out.
    - on_clock_in(): se llama cuando el trabajador ficha entrada correctamente.
    - on_clock_out(): se llama cuando el trabajador ficha salida correctamente.
    """

    phone = is_phone(page)
    field_w = None if phone else 280
    card_w = None if phone else 400
    card_pad = 24 if phone else 40

    code_field = ft.TextField(
        label="Ingresa tu código",
        width=field_w,
        expand=phone,
        password=True,
        can_reveal_password=True,
        border_color=PRIMARY,
        focused_border_color=PRIMARY_DARK,
        prefix_icon=ft.Icons.PIN,
        text_size=BODY_SIZE,
        text_align=ft.TextAlign.CENTER,
    )

    status_text = ft.Text("", size=BODY_SIZE)

    def get_active_record(session) -> ClockRecord | None:
        return (
            session.query(ClockRecord)
            .filter_by(user_id=user.id, clock_out=None)
            .first()
        )

    def do_clock_in(e):
        code = code_field.value.strip()
        if code != user.clock_code:
            status_text.value = "Código incorrecto"
            status_text.color = ERROR
            page.update()
            return

        session = get_session()
        try:
            active = get_active_record(session)
            if active:
                status_text.value = "Ya tienes un turno abierto"
                status_text.color = ERROR
                page.update()
                return

            record = ClockRecord(user_id=user.id, clock_in=datetime.now())
            session.add(record)
            session.commit()
            code_field.value = ""
            status_text.value = f"✓ Clock In registrado a las {datetime.now().strftime('%H:%M')}"
            status_text.color = SUCCESS
            page.update()
            on_clock_in()
        finally:
            session.close()

    def do_clock_out(e):
        code = code_field.value.strip()
        if code != user.clock_code:
            status_text.value = "Código incorrecto"
            status_text.color = ERROR
            page.update()
            return

        session = get_session()
        try:
            active = get_active_record(session)
            if not active:
                status_text.value = "No tienes un turno abierto"
                status_text.color = ERROR
                page.update()
                return

            active.clock_out = datetime.now()
            hours = active.hours_worked
            session.commit()
            code_field.value = ""
            status_text.value = f"✓ Clock Out registrado. Horas trabajadas: {hours:.2f}h"
            status_text.color = SUCCESS
            page.update()
            on_clock_out()
        finally:
            session.close()

    # Check current status
    session = get_session()
    try:
        active_record = get_active_record(session)
        if active_record:
            current_status = ft.Text(
                f"Turno activo desde {active_record.clock_in.strftime('%H:%M')}",
                size=BODY_SIZE,
                color=SUCCESS,
                italic=True,
            )
        else:
            current_status = ft.Text(
                "Sin turno activo",
                size=BODY_SIZE,
                color=TEXT_SECONDARY,
                italic=True,
            )
    finally:
        session.close()

    clock_in_btn = ft.ElevatedButton(
        content=ft.Row([ft.Icon(ft.Icons.LOGIN, color="white", size=18), ft.Text("Clock In", color="white")], spacing=6, tight=True),
        width=None if phone else 130,
        expand=phone,
        height=45,
        bgcolor=SUCCESS,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
        on_click=do_clock_in,
    )

    clock_out_btn = ft.ElevatedButton(
        content=ft.Row([ft.Icon(ft.Icons.LOGOUT, color="white", size=18), ft.Text("Clock Out", color="white")], spacing=6, tight=True),
        width=None if phone else 130,
        expand=phone,
        height=45,
        bgcolor=ERROR,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
        on_click=do_clock_out,
    )

    clock_card = ft.Container(
        content=ft.Column(
            [
                ft.Icon(ft.Icons.ACCESS_TIME, size=50, color=PRIMARY),
                ft.Text(
                    f"Hola, {user.name}",
                    size=SUBTITLE_SIZE,
                    weight=ft.FontWeight.BOLD,
                    color=PRIMARY_DARK,
                    font_family=FONT_FAMILY,
                ),
                current_status,
                ft.Divider(height=15, color="transparent"),
                code_field,
                status_text,
                ft.Divider(height=10, color="transparent"),
                ft.Row(
                    [clock_in_btn, clock_out_btn],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=20,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
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
        content=clock_card,
        alignment=ft.Alignment(0, 0),
        expand=True,
        bgcolor="#E3F2FD",
    )
