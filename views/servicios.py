import flet as ft
from datetime import date, timedelta
from database.db import get_session
from database.models import Service
from components.confirm_dialog import confirm_delete_dialog
from utils.responsive import is_mobile, r_padding, r_font_title, r_dialog_width, r_field_width, is_phone
from assets.styles import (
    PRIMARY, PRIMARY_DARK, SURFACE, SUCCESS, ERROR, ACCENT, SUBTITLE_SIZE,
    TEXT_PRIMARY, TEXT_SECONDARY, TITLE_SIZE, BODY_SIZE, SMALL_SIZE, DIVIDER_COLOR,
)

SERVICE_NAMES = ["Agua", "Corriente", "Basura"]


def servicios_view(page: ft.Page, user):
    """Módulo de Servicios: agua, corriente, basura — con CRUD."""

    content_area = ft.Ref[ft.Column]()

    def _load_services():
        session = get_session()
        try:
            upcoming = session.query(Service).filter(Service.is_paid == False).order_by(Service.due_date).all()
            paid = session.query(Service).filter(Service.is_paid == True).order_by(Service.due_date.desc()).limit(15).all()
            up_list = [{"id": s.id, "name": s.name, "due_date": s.due_date, "amount": s.amount,
                        "is_paid": s.is_paid, "paid_date": s.paid_date} for s in upcoming]
            pd_list = [{"id": s.id, "name": s.name, "due_date": s.due_date, "amount": s.amount,
                        "is_paid": s.is_paid, "paid_date": s.paid_date} for s in paid]
            return up_list, pd_list
        finally:
            session.close()

    def _refresh():
        content_area.current.controls.clear()
        content_area.current.controls.extend(_build_content())
        content_area.current.update()

    # ── dialogs ──

    def _add_service_dialog():
        ph = is_phone(page)
        name_dd = ft.Dropdown(
            label="Servicio", width=r_field_width(page, 200), expand=ph,
            options=[ft.dropdown.Option(n) for n in SERVICE_NAMES],
            value=SERVICE_NAMES[0], border_color=PRIMARY, text_size=BODY_SIZE,
        )
        amount_field = ft.TextField(
            label="Monto ($)", width=r_field_width(page, 150), expand=ph, text_size=BODY_SIZE, border_color=PRIMARY,
            prefix_icon=ft.Icons.ATTACH_MONEY,
            input_filter=ft.InputFilter(regex_string=r"[0-9.]", allow=True),
            autofocus=True,
        )
        due_field = ft.TextField(
            label="Fecha límite (DD/MM/YYYY)", width=r_field_width(page, 200), expand=ph, text_size=BODY_SIZE, border_color=PRIMARY,
            hint_text="ej: 15/05/2026",
        )
        status_text = ft.Text("", size=BODY_SIZE)

        def _save(e):
            try:
                amount = float(amount_field.value or 0)
            except ValueError:
                amount = 0.0

            due_val = due_field.value.strip() if due_field.value else ""
            if not due_val:
                status_text.value = "Ingresa la fecha límite"
                status_text.color = ERROR
                page.update()
                return
            try:
                parts = due_val.split("/")
                due = date(int(parts[2]), int(parts[1]), int(parts[0]))
            except (ValueError, IndexError):
                status_text.value = "Fecha inválida. Formato: DD/MM/YYYY"
                status_text.color = ERROR
                page.update()
                return

            session = get_session()
            try:
                svc = Service(name=name_dd.value, due_date=due, amount=amount if amount > 0 else None)
                session.add(svc)
                session.commit()
                page.pop_dialog()
                _refresh()
            except Exception as ex:
                session.rollback()
                status_text.value = f"Error: {str(ex)}"
                status_text.color = ERROR
                page.update()
            finally:
                session.close()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Nuevo Servicio", size=SUBTITLE_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
            content=ft.Container(
                content=ft.Column([name_dd, amount_field, due_field, status_text], spacing=14),
                width=r_dialog_width(page, 380), height=None if ph else 220,
            ),
            actions=[
                ft.TextButton(content=ft.Text("Cancelar"), on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton(content=ft.Text("Guardar", color="white"), bgcolor=SUCCESS,
                                  style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)), on_click=_save),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(dlg)

    def _mark_paid(sid: int):
        session = get_session()
        try:
            s = session.query(Service).get(sid)
            if s:
                s.is_paid = True
                s.paid_date = date.today()
                session.commit()
        finally:
            session.close()
        _refresh()

    def _mark_unpaid(sid: int):
        session = get_session()
        try:
            s = session.query(Service).get(sid)
            if s:
                s.is_paid = False
                s.paid_date = None
                session.commit()
        finally:
            session.close()
        _refresh()

    def _delete_service(sid: int, name: str):
        def _do():
            session = get_session()
            try:
                s = session.query(Service).get(sid)
                if s:
                    session.delete(s)
                    session.commit()
            finally:
                session.close()
            _refresh()
        confirm_delete_dialog(page, "Eliminar Servicio", f"¿Eliminar el pago de {name}?", _do)

    # ── UI builders ──

    def _service_card(s):
        days_left = (s["due_date"] - date.today()).days
        is_overdue = s["due_date"] < date.today() and not s["is_paid"]

        if s["is_paid"]:
            status_color = SUCCESS
            icon = ft.Icons.CHECK_CIRCLE
            status_label = f"Pagado el {s['paid_date'].strftime('%d/%m/%Y')}" if s["paid_date"] else "Pagado"
        elif is_overdue:
            status_color = ERROR
            icon = ft.Icons.ERROR
            status_label = f"¡VENCIDO hace {abs(days_left)} días!"
        elif days_left <= 3:
            status_color = ERROR
            icon = ft.Icons.WARNING
            status_label = f"Vence en {days_left} día(s)"
        elif days_left <= 7:
            status_color = ACCENT
            icon = ft.Icons.TIMER
            status_label = f"Vence en {days_left} días"
        else:
            status_color = TEXT_SECONDARY
            icon = ft.Icons.SCHEDULE
            status_label = f"Vence el {s['due_date'].strftime('%d/%m/%Y')}"

        svc_icon = ft.Icons.WATER_DROP
        if "corriente" in s["name"].lower() or "luz" in s["name"].lower():
            svc_icon = ft.Icons.ELECTRIC_BOLT
        elif "basura" in s["name"].lower():
            svc_icon = ft.Icons.DELETE

        action_btn = ft.ElevatedButton(
            content=ft.Text("Marcar Pagado" if not s["is_paid"] else "Desmarcar", color="white"),
            bgcolor=SUCCESS if not s["is_paid"] else TEXT_SECONDARY,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6),
                                 padding=ft.padding.symmetric(horizontal=10, vertical=6)),
            on_click=lambda e, sid=s["id"]: _mark_paid(sid) if not s["is_paid"] else _mark_unpaid(sid),
        )

        return ft.Container(
            content=ft.Row([
                ft.Container(
                    content=ft.Icon(svc_icon, color="white", size=20),
                    width=40, height=40, border_radius=20,
                    bgcolor=status_color, alignment=ft.Alignment(0, 0),
                ),
                ft.Column([
                    ft.Text(s["name"], size=BODY_SIZE, weight=ft.FontWeight.W_500, color=TEXT_PRIMARY),
                    ft.Row([ft.Icon(icon, color=status_color, size=14),
                            ft.Text(status_label, size=SMALL_SIZE, color=status_color)], spacing=4),
                ], spacing=2, expand=True),
                ft.Text(f"${s['amount']:,.2f}" if s["amount"] else "—",
                        size=BODY_SIZE, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                action_btn,
                ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=16, icon_color=ERROR, tooltip="Eliminar",
                              on_click=lambda e, sid=s["id"], nm=s["name"]: _delete_service(sid, nm)),
            ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=14, border_radius=10, bgcolor=SURFACE,
            border=ft.border.all(1, status_color if not s["is_paid"] and days_left <= 3 else DIVIDER_COLOR),
        )

    def _section(title, icon, controls):
        return ft.Container(
            content=ft.Column([
                ft.Row([ft.Icon(icon, color=PRIMARY_DARK, size=20),
                        ft.Text(title, size=BODY_SIZE, weight=ft.FontWeight.W_600, color=TEXT_PRIMARY)], spacing=8),
                ft.Divider(height=1, color=DIVIDER_COLOR),
                *controls,
            ], spacing=8),
            padding=16, border_radius=12, bgcolor=SURFACE,
            shadow=ft.BoxShadow(spread_radius=0, blur_radius=8,
                                color=ft.Colors.with_opacity(0.1, "black"), offset=ft.Offset(0, 2)),
        )

    def _build_content():
        upcoming, paid = _load_services()

        upcoming_items = [_service_card(s) for s in upcoming] if upcoming else [
            ft.Text("No hay servicios pendientes", size=SMALL_SIZE, color=TEXT_SECONDARY, italic=True)
        ]
        paid_items = [_service_card(s) for s in paid] if paid else [
            ft.Text("Sin pagos registrados", size=SMALL_SIZE, color=TEXT_SECONDARY, italic=True)
        ]

        return [
            _section(f"Pagos Pendientes ({len(upcoming)})", ft.Icons.PENDING_ACTIONS, upcoming_items),
            _section(f"Pagos Realizados (últimos 15)", ft.Icons.HISTORY, paid_items),
        ]

    initial_content = _build_content()

    return ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Column([
                    ft.Text("Servicios", size=r_font_title(page), weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
                    ft.Text("Agua, corriente y basura — pagos y recordatorios", size=BODY_SIZE, color=TEXT_SECONDARY),
                ], spacing=4, expand=True),
                ft.ElevatedButton(
                    content=ft.Row([ft.Icon(ft.Icons.ADD, size=16, color="white"),
                                    ft.Text("Nuevo Pago", size=SMALL_SIZE, color="white")], spacing=4),
                    bgcolor=SUCCESS, on_click=lambda e: _add_service_dialog(),
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6),
                                         padding=ft.padding.symmetric(horizontal=12, vertical=8)),
                ),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Container(height=8),
            ft.Column(initial_content, ref=content_area, spacing=16, scroll=ft.ScrollMode.AUTO, expand=True),
        ], expand=True),
        padding=r_padding(page), expand=True,
    )
