import flet as ft
from datetime import date, datetime
from database.db import get_session
from database.models import Order, OrderStatus
from components.confirm_dialog import confirm_delete_dialog
from utils.responsive import is_mobile, r_padding, r_font_title, r_dialog_width
from assets.styles import (
    PRIMARY, PRIMARY_DARK, SURFACE, SUCCESS, ERROR, ACCENT,
    TEXT_PRIMARY, TEXT_SECONDARY, TITLE_SIZE, BODY_SIZE, SMALL_SIZE, DIVIDER_COLOR,
)


def pedidos_view(page: ft.Page, user):
    """Módulo de Pedidos: CRUD de pedidos a proveedores."""

    show_only_pending = True
    content_area = ft.Ref[ft.Column]()

    def _load_orders():
        session = get_session()
        try:
            q = session.query(Order).order_by(Order.order_date.desc())
            if show_only_pending:
                q = q.filter(Order.status == OrderStatus.PENDING)
            orders = q.all()
            return [{"id": o.id, "provider": o.provider, "description": o.description or "",
                     "amount": o.amount, "order_date": o.order_date,
                     "status": o.status} for o in orders]
        finally:
            session.close()

    def _refresh():
        content_area.current.controls.clear()
        content_area.current.controls.extend(_build_content())
        content_area.current.update()

    # ---- Order dialog (create / edit) ----
    def _open_order_dialog(order_id=None):
        editing = order_id is not None
        existing = None
        if editing:
            session = get_session()
            try:
                o = session.query(Order).get(order_id)
                if o:
                    existing = {"provider": o.provider, "description": o.description or "",
                                "amount": o.amount, "order_date": o.order_date, "status": o.status}
            finally:
                session.close()

        provider_field = ft.TextField(label="Proveedor", value=existing["provider"] if existing else "",
                                      border_radius=8, text_size=BODY_SIZE)
        desc_field = ft.TextField(label="Descripción", value=existing["description"] if existing else "",
                                  border_radius=8, text_size=BODY_SIZE, multiline=True, min_lines=2, max_lines=4)
        amount_field = ft.TextField(label="Monto ($)", value=str(existing["amount"]) if existing and existing["amount"] else "",
                                    border_radius=8, text_size=BODY_SIZE, keyboard_type=ft.KeyboardType.NUMBER)
        date_field = ft.TextField(label="Fecha (DD/MM/YYYY)",
                                  value=existing["order_date"].strftime("%d/%m/%Y") if existing else date.today().strftime("%d/%m/%Y"),
                                  border_radius=8, text_size=BODY_SIZE)
        error_text = ft.Text("", color=ERROR, size=SMALL_SIZE)

        def _save(e):
            prov = provider_field.value.strip()
            if not prov:
                error_text.value = "Proveedor requerido"
                dlg.update()
                return
            try:
                d = datetime.strptime(date_field.value.strip(), "%d/%m/%Y").date()
            except ValueError:
                error_text.value = "Fecha inválida (DD/MM/YYYY)"
                dlg.update()
                return
            amt = None
            if amount_field.value.strip():
                try:
                    amt = float(amount_field.value.strip())
                except ValueError:
                    error_text.value = "Monto inválido"
                    dlg.update()
                    return

            session = get_session()
            try:
                if editing:
                    o = session.query(Order).get(order_id)
                    if o:
                        o.provider = prov
                        o.description = desc_field.value.strip()
                        o.amount = amt
                        o.order_date = d
                else:
                    o = Order(provider=prov, description=desc_field.value.strip(),
                              amount=amt, order_date=d)
                    session.add(o)
                session.commit()
            finally:
                session.close()

            page.pop_dialog()
            _refresh()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Editar Pedido" if editing else "Nuevo Pedido", size=BODY_SIZE, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column([provider_field, desc_field, amount_field, date_field, error_text],
                                  spacing=12, tight=True),
                width=r_dialog_width(page, 380),
            ),
            actions=[
                ft.TextButton(content=ft.Text("Cancelar"), on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton(content=ft.Text("Guardar", color="white"), bgcolor=PRIMARY, on_click=_save),
            ],
        )
        page.show_dialog(dlg)

    # ---- Toggle status ----
    def _toggle_status(oid: int):
        session = get_session()
        try:
            o = session.query(Order).get(oid)
            if o:
                o.status = OrderStatus.RECEIVED if o.status == OrderStatus.PENDING else OrderStatus.PENDING
                session.commit()
        finally:
            session.close()
        _refresh()

    # ---- Delete ----
    def _delete_order(oid: int):
        def _do():
            session = get_session()
            try:
                o = session.query(Order).get(oid)
                if o:
                    session.delete(o)
                    session.commit()
            finally:
                session.close()
            _refresh()
        confirm_delete_dialog(page, "Eliminar Pedido", "¿Eliminar este pedido?", _do)

    # ---- Order row ----
    def _order_row(o):
        is_pending = o["status"] == OrderStatus.PENDING
        status_color = ACCENT if is_pending else SUCCESS
        status_label = "Pendiente" if is_pending else "Recibido"
        amt_text = f"${o['amount']:,.2f}" if o["amount"] else "—"
        return ft.Container(
            content=ft.Row([
                ft.Container(
                    content=ft.Text(status_label, size=SMALL_SIZE, color="white", weight=ft.FontWeight.W_500),
                    bgcolor=status_color, border_radius=6,
                    padding=ft.padding.symmetric(horizontal=8, vertical=3),
                ),
                ft.Column([
                    ft.Text(o["provider"], size=BODY_SIZE, weight=ft.FontWeight.W_600, color=TEXT_PRIMARY),
                    ft.Text(o["description"] if o["description"] else "Sin descripción",
                            size=SMALL_SIZE, color=TEXT_SECONDARY, max_lines=1),
                ], spacing=2, expand=True),
                ft.Text(o["order_date"].strftime("%d/%m/%Y"), size=SMALL_SIZE, color=TEXT_SECONDARY),
                ft.Text(amt_text, size=BODY_SIZE, weight=ft.FontWeight.BOLD, color=ACCENT),
                ft.IconButton(ft.Icons.CHECK_CIRCLE_OUTLINE if is_pending else ft.Icons.UNDO,
                              icon_size=18, icon_color=SUCCESS if is_pending else ACCENT,
                              tooltip="Marcar Recibido" if is_pending else "Marcar Pendiente",
                              on_click=lambda e, oid=o["id"]: _toggle_status(oid)),
                ft.IconButton(ft.Icons.EDIT, icon_size=16, icon_color=PRIMARY, tooltip="Editar",
                              on_click=lambda e, oid=o["id"]: _open_order_dialog(oid)),
                ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=16, icon_color=ERROR, tooltip="Eliminar",
                              on_click=lambda e, oid=o["id"]: _delete_order(oid)),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.symmetric(vertical=6, horizontal=4),
        )

    # ---- Toggle filter ----
    def _toggle_filter(e):
        nonlocal show_only_pending
        show_only_pending = not show_only_pending
        _refresh()

    # ---- Build ----
    def _build_content():
        orders = _load_orders()
        rows = [_order_row(o) for o in orders]
        if not rows:
            rows = [ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.CHECK_CIRCLE, size=40, color=TEXT_SECONDARY),
                    ft.Text("Sin pedidos pendientes" if show_only_pending else "Sin pedidos",
                            size=BODY_SIZE, color=TEXT_SECONDARY),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                padding=40, alignment=ft.Alignment(0, 0),
            )]

        pending_count = 0
        if not show_only_pending:
            session = get_session()
            try:
                pending_count = session.query(Order).filter(Order.status == OrderStatus.PENDING).count()
            finally:
                session.close()
        else:
            pending_count = len(orders)

        summary = ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Text("Pendientes", size=SMALL_SIZE, color=TEXT_SECONDARY),
                    ft.Text(str(pending_count), size=TITLE_SIZE, weight=ft.FontWeight.BOLD, color=ACCENT),
                ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
                ft.Column([
                    ft.Text("Total registros", size=SMALL_SIZE, color=TEXT_SECONDARY),
                    ft.Text(str(len(orders)), size=TITLE_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY),
                ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
            ], alignment=ft.MainAxisAlignment.SPACE_AROUND),
            padding=16, border_radius=12, bgcolor=SURFACE,
            shadow=ft.BoxShadow(spread_radius=0, blur_radius=8,
                                color=ft.Colors.with_opacity(0.1, "black"), offset=ft.Offset(0, 2)),
        )

        list_section = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.SHOPPING_CART, color=PRIMARY_DARK, size=20),
                    ft.Text(f"Pedidos ({len(orders)})", size=BODY_SIZE, weight=ft.FontWeight.W_600,
                            color=TEXT_PRIMARY, expand=True),
                    ft.TextButton(
                        "Ver todos" if show_only_pending else "Solo pendientes",
                        on_click=_toggle_filter,
                        style=ft.ButtonStyle(color=PRIMARY),
                    ),
                ], spacing=8),
                ft.Divider(height=1, color=DIVIDER_COLOR),
                *rows,
            ], spacing=8),
            padding=16, border_radius=12, bgcolor=SURFACE,
            shadow=ft.BoxShadow(spread_radius=0, blur_radius=8,
                                color=ft.Colors.with_opacity(0.1, "black"), offset=ft.Offset(0, 2)),
        )

        return [summary, list_section]

    initial_content = _build_content()

    return ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Column([
                    ft.Text("Pedidos", size=r_font_title(page), weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
                    ft.Text("Gestión de pedidos a proveedores", size=BODY_SIZE, color=TEXT_SECONDARY),
                ], spacing=4, expand=True),
                ft.ElevatedButton(
                    content=ft.Row([ft.Icon(ft.Icons.ADD, size=16, color="white"),
                                    ft.Text("Nuevo Pedido", size=SMALL_SIZE, color="white")], spacing=4),
                    bgcolor=ACCENT, on_click=lambda e: _open_order_dialog(),
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6),
                                         padding=ft.padding.symmetric(horizontal=12, vertical=8)),
                ),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Container(height=8),
            ft.Column(initial_content, ref=content_area, spacing=16, scroll=ft.ScrollMode.AUTO, expand=True),
        ], expand=True),
        padding=r_padding(page), expand=True,
    )
