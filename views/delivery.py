import flet as ft
from datetime import date
from database.db import get_session
from database.models import FuelDelivery
from components.calendar_picker import calendar_picker
from components.date_field import make_date_field
from components.confirm_dialog import confirm_delete_dialog
from utils.responsive import is_mobile, responsive_layout, r_padding, r_font_title, r_calendar_width, r_dialog_width, r_field_width, is_phone
from assets.styles import (
    PRIMARY, PRIMARY_DARK, SURFACE, SUCCESS, ERROR, ACCENT, SUBTITLE_SIZE,
    TEXT_PRIMARY, TEXT_SECONDARY, TITLE_SIZE, BODY_SIZE, SMALL_SIZE, DIVIDER_COLOR,
)


def delivery_view(page: ft.Page, user):
    """Módulo de Delivery de Gasolina: CRUD completo de entregas."""

    selected_date = date.today()
    content_area = ft.Ref[ft.Column]()

    def _load_deliveries(d: date):
        session = get_session()
        try:
            first = d.replace(day=1)
            if d.month == 12:
                next_m = d.replace(year=d.year + 1, month=1, day=1)
            else:
                next_m = d.replace(month=d.month + 1, day=1)
            deliveries = session.query(FuelDelivery).filter(
                FuelDelivery.delivery_date >= first,
                FuelDelivery.delivery_date < next_m,
            ).order_by(FuelDelivery.delivery_date.desc()).all()
            result = [{"id": dl.id, "delivery_date": dl.delivery_date,
                       "gallons": dl.gallons, "notes": dl.notes} for dl in deliveries]
            total_gallons = sum(dl["gallons"] for dl in result)
            return result, total_gallons
        finally:
            session.close()

    def _refresh():
        content_area.current.controls.clear()
        content_area.current.controls.extend(_build_content(selected_date))
        content_area.current.update()

    # ── dialogs ──

    def _delivery_dialog(delivery_id: int | None = None):
        existing = None
        if delivery_id:
            session = get_session()
            try:
                existing = session.query(FuelDelivery).get(delivery_id)
                ex_data = {"delivery_date": existing.delivery_date, "gallons": existing.gallons, "notes": existing.notes}
            finally:
                session.close()
        else:
            ex_data = None

        ph = is_phone(page)
        date_field = make_date_field(
            "Fecha", width=r_field_width(page, 200), expand=ph, text_size=BODY_SIZE, border_color=PRIMARY,
            value=ex_data["delivery_date"].strftime("%d/%m/%Y") if ex_data else date.today().strftime("%d/%m/%Y"),
            autofocus=True,
        )
        gallons_field = ft.TextField(
            label="Galones", width=r_field_width(page, 150), expand=ph, text_size=BODY_SIZE, border_color=PRIMARY,
            input_filter=ft.InputFilter(regex_string=r"[0-9.]", allow=True),
            value=f"{ex_data['gallons']:.0f}" if ex_data else "",
        )
        notes_field = ft.TextField(
            label="Notas (opcional)", width=r_field_width(page, 400), expand=ph, text_size=BODY_SIZE, border_color=PRIMARY,
            value=ex_data["notes"] or "" if ex_data else "",
        )
        status_text = ft.Text("", size=BODY_SIZE)

        def _save(e):
            date_val = date_field.value.strip()
            try:
                parts = date_val.split("/")
                d_date = date(int(parts[2]), int(parts[1]), int(parts[0]))
            except (ValueError, IndexError):
                status_text.value = "Fecha inválida. Formato: DD/MM/YYYY"
                status_text.color = ERROR
                page.update()
                return

            try:
                gallons = float(gallons_field.value or 0)
            except ValueError:
                gallons = 0
            if gallons <= 0:
                status_text.value = "Los galones deben ser mayor a 0"
                status_text.color = ERROR
                page.update()
                return

            session = get_session()
            try:
                if delivery_id:
                    dl = session.query(FuelDelivery).get(delivery_id)
                    dl.delivery_date = d_date
                    dl.gallons = gallons
                    dl.notes = notes_field.value.strip() if notes_field.value else None
                else:
                    dl = FuelDelivery(
                        delivery_date=d_date,
                        gallons=gallons,
                        notes=notes_field.value.strip() if notes_field.value else None,
                    )
                    session.add(dl)
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

        title = "Editar Entrega" if delivery_id else "Nueva Entrega"
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(title, size=SUBTITLE_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
            content=ft.Container(
                content=ft.Column([ft.Row([date_field, gallons_field], spacing=12), notes_field, status_text], spacing=14),
                width=r_dialog_width(page, 440), height=None if ph else 170,
            ),
            actions=[
                ft.TextButton(content=ft.Text("Cancelar"), on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton(content=ft.Text("Guardar", color="white"), bgcolor=SUCCESS,
                                  style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)), on_click=_save),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(dlg)

    def _delete_delivery(did: int):
        def _do():
            session = get_session()
            try:
                dl = session.query(FuelDelivery).get(did)
                if dl:
                    session.delete(dl)
                    session.commit()
            finally:
                session.close()
            _refresh()
        confirm_delete_dialog(page, "Eliminar Entrega", "¿Eliminar esta entrega de gasolina?", _do)

    # ── UI ──

    def _delivery_row(dl):
        return ft.Container(
            content=ft.Row([
                ft.Container(
                    content=ft.Icon(ft.Icons.LOCAL_SHIPPING, color="white", size=20),
                    width=40, height=40, border_radius=20,
                    bgcolor=ACCENT, alignment=ft.Alignment(0, 0),
                ),
                ft.Column([
                    ft.Text(dl["delivery_date"].strftime("%d/%m/%Y"), size=BODY_SIZE, weight=ft.FontWeight.W_500, color=TEXT_PRIMARY),
                    ft.Text(dl["notes"] or "Sin notas", size=SMALL_SIZE, color=TEXT_SECONDARY),
                ], spacing=2, expand=True),
                ft.Column([
                    ft.Text(f"{dl['gallons']:,.0f}", size=SUBTITLE_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
                    ft.Text("galones", size=SMALL_SIZE, color=TEXT_SECONDARY),
                ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.END),
                ft.IconButton(ft.Icons.EDIT, icon_size=16, icon_color=PRIMARY, tooltip="Editar",
                              on_click=lambda e, did=dl["id"]: _delivery_dialog(did)),
                ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=16, icon_color=ERROR, tooltip="Eliminar",
                              on_click=lambda e, did=dl["id"]: _delete_delivery(did)),
            ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=14, border_radius=10, bgcolor=SURFACE,
            border=ft.border.all(1, DIVIDER_COLOR),
        )

    def _build_content(d: date):
        deliveries, total = _load_deliveries(d)

        summary = ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Text("Total del Mes", size=BODY_SIZE, color=TEXT_SECONDARY),
                    ft.Text(f"{total:,.0f} galones", size=SUBTITLE_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
                ], spacing=4, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
                ft.Column([
                    ft.Text("Entregas", size=BODY_SIZE, color=TEXT_SECONDARY),
                    ft.Text(str(len(deliveries)), size=SUBTITLE_SIZE, weight=ft.FontWeight.BOLD, color=ACCENT),
                ], spacing=4, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
            ], alignment=ft.MainAxisAlignment.SPACE_AROUND),
            padding=20, border_radius=12, bgcolor=SURFACE,
            shadow=ft.BoxShadow(spread_radius=0, blur_radius=8,
                                color=ft.Colors.with_opacity(0.1, "black"), offset=ft.Offset(0, 2)),
        )

        delivery_items = [_delivery_row(dl) for dl in deliveries] if deliveries else [
            ft.Container(
                content=ft.Text("Sin entregas registradas este mes", size=BODY_SIZE, color=TEXT_SECONDARY, italic=True),
                padding=20, alignment=ft.Alignment(0, 0),
            )
        ]

        return [summary, *delivery_items]

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
                ft.Text("Delivery de Gasolina", size=r_font_title(page), weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
                ft.Text("Entregas de gasolina — día y galones recibidos", size=BODY_SIZE, color=TEXT_SECONDARY),
            ], spacing=4, expand=True),
            ft.ElevatedButton(
                content=ft.Row([ft.Icon(ft.Icons.ADD, size=16, color="white"),
                                ft.Text("Nueva Entrega", size=SMALL_SIZE, color="white")], spacing=4),
                bgcolor=SUCCESS, on_click=lambda e: _delivery_dialog(),
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6),
                                     padding=ft.padding.symmetric(horizontal=12, vertical=8)),
            ),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ft.Container(height=8),
        ft.Column(initial_content, ref=content_area, spacing=12, scroll=ft.ScrollMode.AUTO, expand=True),
    ], expand=True)

    return ft.Container(
        content=responsive_layout(page, main_col, cal),
        padding=r_padding(page), expand=True,
    )
