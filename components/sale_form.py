import flet as ft
from datetime import date
from database.db import get_session
from database.models import Sale, ShiftType
from assets.styles import (
    PRIMARY, PRIMARY_DARK, SURFACE, SUCCESS, ERROR, ACCENT,
    TEXT_PRIMARY, TEXT_SECONDARY, SUBTITLE_SIZE, BODY_SIZE, SMALL_SIZE,
)
from utils.responsive import r_dialog_width, r_field_width, is_phone


def sale_form_dialog(page: ft.Page, user_id: int, on_saved, sale_id: int | None = None):
    """Diálogo para registrar o editar una venta."""

    # Si sale_id, cargar datos existentes
    existing = None
    if sale_id:
        session = get_session()
        try:
            existing = session.query(Sale).get(sale_id)
        finally:
            session.close()

    phone = is_phone(page)
    fw = r_field_width(page, 200)
    fw_lg = r_field_width(page, 400)
    dw = r_dialog_width(page, 450)

    shift_dropdown = ft.Dropdown(
        label="Turno",
        width=fw,
        expand=phone,
        options=[
            ft.dropdown.Option(key="morning", text="Mañana"),
            ft.dropdown.Option(key="night", text="Noche"),
        ],
        value=existing.shift.value if existing else "morning",
        border_color=PRIMARY,
        text_size=BODY_SIZE,
    )

    amount_field = ft.TextField(
        label="Monto de la venta ($)",
        width=fw,
        expand=phone,
        text_size=BODY_SIZE,
        border_color=PRIMARY,
        prefix_icon=ft.Icons.ATTACH_MONEY,
        input_filter=ft.InputFilter(regex_string=r"[0-9.]", allow=True),
        autofocus=True,
        value=f"{existing.amount:.2f}" if existing else "",
    )

    desc_field = ft.TextField(
        label="Descripción (opcional)",
        width=fw_lg,
        expand=phone,
        text_size=BODY_SIZE,
        border_color=PRIMARY,
        value=existing.description or "" if existing else "",
    )

    is_cafeteria = ft.Checkbox(
        label="Venta de Cafetería",
        value=existing.is_cafeteria if existing else False,
    )

    status_text = ft.Text("", size=BODY_SIZE)

    def _save(e):
        try:
            amount = float(amount_field.value or 0)
        except ValueError:
            status_text.value = "Monto inválido"
            status_text.color = ERROR
            page.update()
            return

        if amount <= 0:
            status_text.value = "El monto debe ser mayor a $0"
            status_text.color = ERROR
            page.update()
            return

        shift = ShiftType.MORNING if shift_dropdown.value == "morning" else ShiftType.NIGHT

        session = get_session()
        try:
            if sale_id:
                sale = session.query(Sale).get(sale_id)
                sale.shift = shift
                sale.description = desc_field.value.strip() if desc_field.value else None
                sale.amount = amount
                sale.is_cafeteria = is_cafeteria.value
            else:
                sale = Sale(
                    date=date.today(),
                    shift=shift,
                    description=desc_field.value.strip() if desc_field.value else None,
                    amount=amount,
                    is_cafeteria=is_cafeteria.value,
                    user_id=user_id,
                )
                session.add(sale)
            session.commit()
            page.pop_dialog()
            on_saved()
        except Exception as ex:
            session.rollback()
            status_text.value = f"Error: {str(ex)}"
            status_text.color = ERROR
            page.update()
        finally:
            session.close()

    title_text = "Editar Venta" if sale_id else "Registrar Venta"

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Row([
            ft.Icon(ft.Icons.POINT_OF_SALE, color=SUCCESS, size=24),
            ft.Text(title_text, size=SUBTITLE_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
        ], spacing=8),
        content=ft.Container(
            content=ft.Column([
                ft.Row([shift_dropdown, is_cafeteria], spacing=16,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                amount_field,
                desc_field,
                status_text,
            ], spacing=16),
            width=dw,
            height=None if phone else 220,
        ),
        actions=[
            ft.TextButton(content=ft.Text("Cancelar"), on_click=lambda e: page.pop_dialog()),
            ft.ElevatedButton(
                content=ft.Row([ft.Icon(ft.Icons.SAVE, size=18, color="white"),
                                ft.Text("Guardar", color="white", size=BODY_SIZE)], spacing=6),
                bgcolor=SUCCESS,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8),
                                     padding=ft.padding.symmetric(horizontal=20, vertical=12)),
                on_click=_save,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    page.show_dialog(dlg)
