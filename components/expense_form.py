import flet as ft
from datetime import date
from database.db import get_session
from database.models import Expense
from assets.styles import (
    PRIMARY, PRIMARY_DARK, SURFACE, SUCCESS, ERROR, ACCENT,
    TEXT_PRIMARY, TEXT_SECONDARY, SUBTITLE_SIZE, BODY_SIZE, SMALL_SIZE,
)
from utils.responsive import r_dialog_width, r_field_width, is_phone


def expense_form_dialog(page: ft.Page, on_saved, expense_id: int | None = None):
    """Diálogo para registrar o editar un gasto."""

    existing = None
    if expense_id:
        session = get_session()
        try:
            existing = session.query(Expense).get(expense_id)
        finally:
            session.close()

    phone = is_phone(page)
    fw = r_field_width(page, 200)
    fw_lg = r_field_width(page, 400)
    dw = r_dialog_width(page, 450)

    amount_field = ft.TextField(
        label="Monto del gasto ($)",
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
        label="Descripción",
        width=fw_lg,
        expand=phone,
        text_size=BODY_SIZE,
        border_color=PRIMARY,
        value=existing.description if existing else "",
    )

    is_merchandise = ft.Checkbox(
        label="Pago de mercancía",
        value=existing.is_merchandise if existing else False,
    )

    status_text = ft.Text("", size=BODY_SIZE)

    def _save(e):
        desc = desc_field.value.strip() if desc_field.value else ""
        if not desc:
            status_text.value = "Escribe una descripción"
            status_text.color = ERROR
            page.update()
            return

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

        session = get_session()
        try:
            if expense_id:
                expense = session.query(Expense).get(expense_id)
                expense.description = desc
                expense.amount = amount
                expense.is_merchandise = is_merchandise.value
            else:
                expense = Expense(
                    date=date.today(),
                    description=desc,
                    amount=amount,
                    is_merchandise=is_merchandise.value,
                )
                session.add(expense)
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

    title_text = "Editar Gasto" if expense_id else "Registrar Gasto"

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Row([
            ft.Icon(ft.Icons.MONEY_OFF, color=ERROR, size=24),
            ft.Text(title_text, size=SUBTITLE_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
        ], spacing=8),
        content=ft.Container(
            content=ft.Column([
                amount_field,
                desc_field,
                is_merchandise,
                status_text,
            ], spacing=16),
            width=dw,
            height=None if phone else 200,
        ),
        actions=[
            ft.TextButton(content=ft.Text("Cancelar"), on_click=lambda e: page.pop_dialog()),
            ft.ElevatedButton(
                content=ft.Row([ft.Icon(ft.Icons.SAVE, size=18, color="white"),
                                ft.Text("Guardar", color="white", size=BODY_SIZE)], spacing=6),
                bgcolor=ERROR,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8),
                                     padding=ft.padding.symmetric(horizontal=20, vertical=12)),
                on_click=_save,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    page.show_dialog(dlg)
