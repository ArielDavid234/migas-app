import flet as ft
from datetime import date
from database.db import get_session
from database.models import Sale, ShiftType
from sqlalchemy import func
from components.calendar_picker import calendar_picker
from components.sale_form import sale_form_dialog
from components.confirm_dialog import confirm_delete_dialog
from utils.responsive import is_mobile, responsive_layout, r_padding, r_font_title, r_calendar_width
from assets.styles import (
    PRIMARY, PRIMARY_DARK, SURFACE, SUCCESS, ERROR, ACCENT, SUBTITLE_SIZE,
    TEXT_PRIMARY, TEXT_SECONDARY, TITLE_SIZE, BODY_SIZE, SMALL_SIZE, DIVIDER_COLOR,
)


def cafeteria_view(page: ft.Page, user):
    """Módulo de Cafetería: ventas de cafetería con CRUD."""

    selected_date = date.today()
    content_area = ft.Ref[ft.Column]()

    def _load_cafe_data(d: date):
        session = get_session()
        try:
            sales = session.query(Sale).filter(
                Sale.date == d, Sale.is_cafeteria == True
            ).order_by(Sale.created_at.desc()).all()
            sales_list = [{"id": s.id, "shift": s.shift, "amount": s.amount,
                           "description": s.description or "", "user_id": s.user_id} for s in sales]

            morning = sum(s["amount"] for s in sales_list if s["shift"] == ShiftType.MORNING)
            night = sum(s["amount"] for s in sales_list if s["shift"] == ShiftType.NIGHT)

            first = d.replace(day=1)
            if d.month == 12:
                next_m = d.replace(year=d.year + 1, month=1, day=1)
            else:
                next_m = d.replace(month=d.month + 1, day=1)
            monthly = session.query(func.coalesce(func.sum(Sale.amount), 0)).filter(
                Sale.date >= first, Sale.date < next_m, Sale.is_cafeteria == True
            ).scalar()

            return {"sales_list": sales_list, "morning": morning, "night": night,
                    "total": morning + night, "monthly": monthly}
        finally:
            session.close()

    def _refresh():
        content_area.current.controls.clear()
        content_area.current.controls.extend(_build_content(selected_date))
        content_area.current.update()

    def _edit_sale(sid: int):
        sale_form_dialog(page, user.id, on_saved=_refresh, sale_id=sid)

    def _delete_sale(sid: int):
        def _do():
            session = get_session()
            try:
                s = session.query(Sale).get(sid)
                if s:
                    session.delete(s)
                    session.commit()
            finally:
                session.close()
            _refresh()
        confirm_delete_dialog(page, "Eliminar Venta", "¿Eliminar esta venta de cafetería?", _do)

    def _add_cafe_sale(e):
        sale_form_dialog(page, user.id, on_saved=_refresh)

    def _row_info(label, value, color=TEXT_PRIMARY):
        return ft.Row([
            ft.Text(label, size=BODY_SIZE, color=TEXT_SECONDARY, expand=True),
            ft.Text(value, size=BODY_SIZE, weight=ft.FontWeight.BOLD, color=color),
        ])

    def _sale_row(s):
        shift_label = "☀ Mañana" if s["shift"] == ShiftType.MORNING else "🌙 Noche"
        desc = s["description"] if s["description"] else "—"
        return ft.Container(
            content=ft.Row([
                ft.Container(
                    content=ft.Text(shift_label, size=SMALL_SIZE, color="white", weight=ft.FontWeight.W_500),
                    bgcolor=SUCCESS if s["shift"] == ShiftType.MORNING else PRIMARY,
                    border_radius=6, padding=ft.padding.symmetric(horizontal=8, vertical=3),
                ),
                ft.Text(desc, size=BODY_SIZE, color=TEXT_SECONDARY, expand=True),
                ft.Text(f"${s['amount']:,.2f}", size=BODY_SIZE, weight=ft.FontWeight.BOLD, color=ACCENT),
                ft.IconButton(ft.Icons.EDIT, icon_size=16, icon_color=PRIMARY, tooltip="Editar",
                              on_click=lambda e, sid=s["id"]: _edit_sale(sid)),
                ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=16, icon_color=ERROR, tooltip="Eliminar",
                              on_click=lambda e, sid=s["id"]: _delete_sale(sid)),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.symmetric(vertical=4),
        )

    def _build_content(d: date):
        data = _load_cafe_data(d)

        # Summary card
        summary = ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Text("Hoy", size=SMALL_SIZE, color=TEXT_SECONDARY),
                    ft.Text(f"${data['total']:,.2f}", size=SUBTITLE_SIZE, weight=ft.FontWeight.BOLD, color=ACCENT),
                ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
                ft.Column([
                    ft.Text("☀ Mañana", size=SMALL_SIZE, color=TEXT_SECONDARY),
                    ft.Text(f"${data['morning']:,.2f}", size=BODY_SIZE, weight=ft.FontWeight.BOLD, color=SUCCESS),
                ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
                ft.Column([
                    ft.Text("🌙 Noche", size=SMALL_SIZE, color=TEXT_SECONDARY),
                    ft.Text(f"${data['night']:,.2f}", size=BODY_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY),
                ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
                ft.Column([
                    ft.Text("Mes", size=SMALL_SIZE, color=TEXT_SECONDARY),
                    ft.Text(f"${data['monthly']:,.2f}", size=BODY_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
                ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
            ], alignment=ft.MainAxisAlignment.SPACE_AROUND),
            padding=16, border_radius=12, bgcolor=SURFACE,
            shadow=ft.BoxShadow(spread_radius=0, blur_radius=8,
                                color=ft.Colors.with_opacity(0.1, "black"), offset=ft.Offset(0, 2)),
        )

        # Sales list
        sale_rows = [_sale_row(s) for s in data["sales_list"]]
        if not sale_rows:
            sale_rows = [ft.Text("Sin ventas de cafetería", size=SMALL_SIZE, color=TEXT_SECONDARY, italic=True)]

        sales_section = ft.Container(
            content=ft.Column([
                ft.Row([ft.Icon(ft.Icons.COFFEE, color=PRIMARY_DARK, size=20),
                        ft.Text(f"Ventas — {d.strftime('%d/%m/%Y')}  ({len(data['sales_list'])} registros)",
                                size=BODY_SIZE, weight=ft.FontWeight.W_600, color=TEXT_PRIMARY)], spacing=8),
                ft.Divider(height=1, color=DIVIDER_COLOR),
                *sale_rows,
            ], spacing=8),
            padding=16, border_radius=12, bgcolor=SURFACE,
            shadow=ft.BoxShadow(spread_radius=0, blur_radius=8,
                                color=ft.Colors.with_opacity(0.1, "black"), offset=ft.Offset(0, 2)),
        )

        return [summary, sales_section]

    def _on_date_selected(d: date):
        nonlocal selected_date
        selected_date = d
        _refresh()

    initial_content = _build_content(selected_date)
    cal = calendar_picker(on_date_selected=_on_date_selected, initial_date=selected_date,
                          cal_width=r_calendar_width(page))

    mobile = is_mobile(page)
    main_col = ft.Column([
        ft.Row([
            ft.Column([
                ft.Text("Cafetería", size=r_font_title(page), weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
                ft.Text("Ventas de cafetería por turno y mes", size=BODY_SIZE, color=TEXT_SECONDARY),
            ], spacing=4, expand=True),
            ft.ElevatedButton(
                content=ft.Row([ft.Icon(ft.Icons.ADD, size=16, color="white"),
                                ft.Text("Registrar Venta", size=SMALL_SIZE, color="white")], spacing=4),
                bgcolor=ACCENT, on_click=_add_cafe_sale,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6),
                                     padding=ft.padding.symmetric(horizontal=12, vertical=8)),
            ),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ft.Container(height=8),
        ft.Column(initial_content, ref=content_area, spacing=16, scroll=ft.ScrollMode.AUTO, expand=True),
    ], expand=True)

    return ft.Container(
        content=responsive_layout(page, main_col, cal),
        padding=r_padding(page), expand=True,
    )
