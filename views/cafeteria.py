import flet as ft
from datetime import date, datetime
from database.db import get_session
from database.models import Sale, ShiftType, LoyaltyCustomer, LoyaltyCafeteriaPurchase, LoyaltyRewardRedemption, Product
from sqlalchemy import func
from components.calendar_picker import calendar_picker
from components.sale_form import sale_form_dialog
from components.confirm_dialog import confirm_delete_dialog
from utils.responsive import is_mobile, responsive_layout, r_padding, r_font_title, r_calendar_width, is_phone, r_dialog_width
from utils.toast import show_toast
from utils.audit import log_action
from config import LOYALTY_PURCHASES_FOR_REWARD
from assets.styles import (
    PRIMARY, PRIMARY_DARK, SURFACE, SUCCESS, ERROR, ACCENT, SUBTITLE_SIZE,
    TEXT_PRIMARY, TEXT_SECONDARY, TITLE_SIZE, BODY_SIZE, SMALL_SIZE, DIVIDER_COLOR,
)


def cafeteria_view(page: ft.Page, user):
    """Módulo de Cafetería: ventas de cafetería con CRUD."""

    selected_date = date.today()
    sales_area = ft.Ref[ft.Column]()

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
        sales_area.current.controls.clear()
        sales_area.current.controls.extend(_build_content(selected_date))
        sales_area.current.update()

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

    # ── Loyalty / Clientes Fidelizados ──────────────────────────

    loyalty_area = ft.Ref[ft.Column]()
    loyalty_search_ref = ft.Ref[ft.TextField]()

    def _loyalty_load(search: str = "") -> list:
        session = get_session()
        try:
            q = session.query(LoyaltyCustomer).filter_by(is_active=True)
            if search.strip():
                q = q.filter(
                    LoyaltyCustomer.name.ilike(f"%{search}%") |
                    LoyaltyCustomer.email.ilike(f"%{search}%")
                )
            customers = q.order_by(LoyaltyCustomer.name).all()
            return [
                {
                    "id": c.id,
                    "name": c.name,
                    "email": c.email,
                    "total": c.total_purchases,
                    "since_reward": c.purchases_since_last_reward,
                    "reward_ready": c.purchases_since_last_reward >= LOYALTY_PURCHASES_FOR_REWARD,
                    "recent": (
                        session.query(LoyaltyCafeteriaPurchase)
                        .filter_by(customer_id=c.id)
                        .order_by(LoyaltyCafeteriaPurchase.purchased_at.desc())
                        .limit(3).all()
                    ),
                }
                for c in customers
            ]
        finally:
            session.close()

    def _loyalty_refresh(search: str = ""):
        loyalty_area.current.controls.clear()
        loyalty_area.current.controls.extend(_loyalty_build(search))
        loyalty_area.current.update()

    def _open_add_customer_dialog():
        ph = is_phone(page)
        w = r_dialog_width(page) - 48 if not ph else None
        name_f = ft.TextField(label="Nombre", expand=ph, width=w, border_color=PRIMARY,
                               text_size=BODY_SIZE, autofocus=True)
        email_f = ft.TextField(label="Correo electrónico", expand=ph, width=w,
                                border_color=PRIMARY, text_size=BODY_SIZE,
                                prefix_icon=ft.Icons.EMAIL)
        err = ft.Text("", color=ERROR, size=SMALL_SIZE)

        def _save(e):
            name = name_f.value.strip()
            email = email_f.value.strip().lower()
            if not name or not email or "@" not in email:
                err.value = "Nombre y correo válido son obligatorios."
                err.update(); return
            session = get_session()
            try:
                if session.query(LoyaltyCustomer).filter_by(email=email).first():
                    err.value = "Ya existe un cliente con ese correo."
                    err.update(); return
                c = LoyaltyCustomer(name=name, email=email)
                session.add(c)
                session.commit()
                log_action(user.id, "CREATE", "LoyaltyCustomer", None, f"{name} <{email}>")
            finally:
                session.close()
            page.pop_dialog()
            show_toast(page, f"Cliente {name} registrado", is_success=True)
            _loyalty_refresh()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([ft.Icon(ft.Icons.PERSON_ADD, color=PRIMARY_DARK, size=24),
                          ft.Text("Nuevo Cliente Fidelizado", size=SUBTITLE_SIZE,
                                  weight=ft.FontWeight.BOLD, color=PRIMARY_DARK)], spacing=8),
            content=ft.Container(
                content=ft.Column([name_f, email_f, err], spacing=10, tight=True),
                width=r_dialog_width(page),
            ),
            actions=[
                ft.TextButton(content=ft.Text("Cancelar"), on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton(
                    content=ft.Text("Registrar", color="white"), bgcolor=PRIMARY,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                    on_click=_save,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(dlg)

    def _show_low_stock_alert(low_items: list):
        rows = [
            ft.DataRow(cells=[
                ft.DataCell(ft.Text(item["name"], size=SMALL_SIZE, color=TEXT_PRIMARY)),
                ft.DataCell(ft.Text(str(item["stock"]), size=SMALL_SIZE,
                                    color=ERROR, weight=ft.FontWeight.W_600)),
                ft.DataCell(ft.Text(str(item["min"]), size=SMALL_SIZE, color=TEXT_SECONDARY)),
            ])
            for item in low_items
        ]
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=ERROR, size=24),
                ft.Text("Stock Bajo en Inventario", size=SUBTITLE_SIZE,
                        weight=ft.FontWeight.BOLD, color=ERROR),
            ], spacing=8),
            content=ft.Container(
                content=ft.Column([
                    ft.Text(
                        f"Hay {len(low_items)} producto(s) con stock igual o por debajo del mínimo:",
                        size=SMALL_SIZE, color=TEXT_SECONDARY,
                    ),
                    ft.Divider(height=1),
                    ft.DataTable(
                        columns=[
                            ft.DataColumn(ft.Text("Producto", size=SMALL_SIZE, weight=ft.FontWeight.W_600)),
                            ft.DataColumn(ft.Text("Stock actual", size=SMALL_SIZE, weight=ft.FontWeight.W_600), numeric=True),
                            ft.DataColumn(ft.Text("Mínimo", size=SMALL_SIZE, weight=ft.FontWeight.W_600), numeric=True),
                        ],
                        rows=rows,
                        border=ft.border.all(1, DIVIDER_COLOR),
                        border_radius=8,
                        heading_row_color=ft.Colors.with_opacity(0.05, ERROR),
                        data_row_min_height=36,
                        column_spacing=16,
                    ),
                ], spacing=10, tight=True, scroll=ft.ScrollMode.AUTO),
                width=r_dialog_width(page),
                height=min(60 + len(low_items) * 40, 320),
            ),
            actions=[
                ft.ElevatedButton(
                    content=ft.Text("Entendido", color="white"), bgcolor=PRIMARY,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                    on_click=lambda e: page.pop_dialog(),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(dlg)

    def _open_register_purchase_dialog(cdata: dict):
        ph = is_phone(page)
        w = r_dialog_width(page) - 48 if not ph else None
        amount_f = ft.TextField(label="Monto de la compra ($)", expand=ph, width=w,
                                 border_color=PRIMARY, text_size=BODY_SIZE,
                                 prefix_icon=ft.Icons.ATTACH_MONEY, autofocus=True)
        notes_f = ft.TextField(label="Descripción (opcional)", expand=ph, width=w,
                                border_color=PRIMARY, text_size=BODY_SIZE)
        err = ft.Text("", color=ERROR, size=SMALL_SIZE)

        remaining = LOYALTY_PURCHASES_FOR_REWARD - cdata["since_reward"]
        progress_text = ft.Text(
            f"Lleva {cdata['since_reward']}/{LOYALTY_PURCHASES_FOR_REWARD} compras — "
            f"{'¡Tiene recompensa disponible!' if cdata['reward_ready'] else f'Faltan {remaining} para recompensa'}",
            size=SMALL_SIZE,
            color=SUCCESS if cdata["reward_ready"] else TEXT_SECONDARY,
        )

        def _save(e):
            try:
                amt = float(amount_f.value or "0")
                if amt < 0:
                    err.value = "El monto no puede ser negativo."
                    err.update(); return
            except ValueError:
                err.value = "Monto inválido."
                err.update(); return

            session = get_session()
            try:
                c = session.query(LoyaltyCustomer).get(cdata["id"])
                if not c:
                    err.value = "Cliente no encontrado."; err.update(); return
                p = LoyaltyCafeteriaPurchase(
                    customer_id=c.id, amount=amt,
                    notes=notes_f.value.strip() or None,
                )
                session.add(p)
                c.total_purchases += 1
                c.purchases_since_last_reward += 1
                session.commit()
                reward_unlocked = c.purchases_since_last_reward >= LOYALTY_PURCHASES_FOR_REWARD
                log_action(user.id, "CREATE", "LoyaltyCafeteriaPurchase", p.id,
                           f"{c.name} — compra #{c.total_purchases} — ${amt:.2f}")
            finally:
                session.close()

            page.pop_dialog()
            if reward_unlocked:
                show_toast(page,
                           f"🎉 {cdata['name']} ha completado {LOYALTY_PURCHASES_FOR_REWARD} compras — ¡Recompensa desbloqueada!",
                           is_success=True)
                # Check low-stock items and notify
                sess2 = get_session()
                try:
                    low = (
                        sess2.query(Product)
                        .filter(Product.stock <= Product.min_stock, Product.stock >= 0)
                        .order_by(Product.stock.asc())
                        .all()
                    )
                    low_items = [{"name": p.name, "stock": p.stock, "min": p.min_stock} for p in low]
                finally:
                    sess2.close()
                if low_items:
                    _show_low_stock_alert(low_items)
            else:
                show_toast(page, f"Compra registrada para {cdata['name']}", is_success=True)
            _loyalty_refresh()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([ft.Icon(ft.Icons.ADD_SHOPPING_CART, color=SUCCESS, size=24),
                          ft.Text(f"Registrar Compra — {cdata['name']}", size=SUBTITLE_SIZE,
                                  weight=ft.FontWeight.BOLD, color=PRIMARY_DARK)], spacing=8),
            content=ft.Container(
                content=ft.Column([progress_text, ft.Divider(height=1),
                                   amount_f, notes_f, err], spacing=10, tight=True),
                width=r_dialog_width(page),
            ),
            actions=[
                ft.TextButton(content=ft.Text("Cancelar"), on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton(
                    content=ft.Text("Registrar Compra", color="white"), bgcolor=SUCCESS,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                    on_click=_save,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(dlg)

    def _open_redeem_dialog(cdata: dict):
        ph = is_phone(page)
        w = r_dialog_width(page) - 48 if not ph else None
        reward_f = ft.TextField(
            label="Tipo de recompensa", expand=ph, width=w,
            border_color=SUCCESS, text_size=BODY_SIZE, autofocus=True,
            hint_text="Ej: Café gratis, Promoción 2x1, Artículo gratis...",
        )
        notes_f = ft.TextField(label="Notas (opcional)", expand=ph, width=w,
                                border_color=SUCCESS, text_size=BODY_SIZE)
        err = ft.Text("", color=ERROR, size=SMALL_SIZE)

        def _save(e):
            reward = reward_f.value.strip()
            if not reward:
                err.value = "Especifica el tipo de recompensa."
                err.update(); return
            session = get_session()
            try:
                c = session.query(LoyaltyCustomer).get(cdata["id"])
                if not c:
                    err.value = "Cliente no encontrado."; err.update(); return
                r = LoyaltyRewardRedemption(
                    customer_id=c.id, reward_type=reward,
                    redeemed_by_user_id=user.id,
                    notes=notes_f.value.strip() or None,
                )
                session.add(r)
                c.purchases_since_last_reward = 0  # reset counter
                session.commit()
                log_action(user.id, "CREATE", "LoyaltyRewardRedemption", r.id,
                           f"{c.name} — canjea: {reward}")
            finally:
                session.close()
            page.pop_dialog()
            show_toast(page, f"Recompensa canjeada para {cdata['name']}", is_success=True)
            _loyalty_refresh()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([ft.Icon(ft.Icons.CARD_GIFTCARD, color=ACCENT, size=24),
                          ft.Text(f"Canjear Recompensa — {cdata['name']}", size=SUBTITLE_SIZE,
                                  weight=ft.FontWeight.BOLD, color=PRIMARY_DARK)], spacing=8),
            content=ft.Container(
                content=ft.Column([
                    ft.Text(
                        f"{cdata['name']} completó {cdata['since_reward']} compras."
                        f" Describe la recompensa que se le entrega:",
                        size=SMALL_SIZE, color=TEXT_SECONDARY,
                    ),
                    ft.Divider(height=1),
                    reward_f, notes_f, err,
                ], spacing=10, tight=True),
                width=r_dialog_width(page),
            ),
            actions=[
                ft.TextButton(content=ft.Text("Cancelar"), on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton(
                    content=ft.Text("Confirmar Canje", color="white"), bgcolor=ACCENT,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                    on_click=_save,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(dlg)

    def _customer_card(cdata: dict) -> ft.Container:
        reward_ready = cdata["reward_ready"]
        since = cdata["since_reward"]
        total = cdata["total"]
        progress_ratio = min(since / LOYALTY_PURCHASES_FOR_REWARD, 1.0)

        progress_bar = ft.ProgressBar(
            value=progress_ratio,
            bgcolor=ft.Colors.with_opacity(0.15, SUCCESS if reward_ready else PRIMARY),
            color=SUCCESS if reward_ready else PRIMARY,
            height=6,
            border_radius=3,
        )

        badge = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.CARD_GIFTCARD, size=13, color="white"),
                ft.Text("¡Recompensa!", size=SMALL_SIZE, color="white", weight=ft.FontWeight.BOLD),
            ], spacing=4),
            bgcolor=SUCCESS,
            border_radius=6,
            padding=ft.padding.symmetric(horizontal=8, vertical=3),
            visible=reward_ready,
        )

        action_row = ft.Row([
            ft.IconButton(
                icon=ft.Icons.ADD_SHOPPING_CART,
                icon_color=PRIMARY, icon_size=20,
                tooltip="Registrar compra",
                on_click=lambda e, c=cdata: _open_register_purchase_dialog(c),
            ),
            ft.IconButton(
                icon=ft.Icons.CARD_GIFTCARD,
                icon_color=SUCCESS if reward_ready else ft.Colors.with_opacity(0.3, SUCCESS),
                icon_size=20,
                tooltip="Canjear recompensa" if reward_ready else f"Faltan {LOYALTY_PURCHASES_FOR_REWARD - since} compras",
                disabled=not reward_ready,
                on_click=lambda e, c=cdata: _open_redeem_dialog(c) if reward_ready else None,
            ),
        ], spacing=0)

        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.PERSON, color=PRIMARY, size=18),
                    ft.Column([
                        ft.Text(cdata["name"], size=BODY_SIZE,
                                weight=ft.FontWeight.W_600, color=TEXT_PRIMARY),
                        ft.Text(cdata["email"], size=SMALL_SIZE, color=TEXT_SECONDARY),
                    ], spacing=1, expand=True),
                    badge,
                    action_row,
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=6),
                ft.Row([
                    ft.Text(f"{since}/{LOYALTY_PURCHASES_FOR_REWARD} compras",
                            size=SMALL_SIZE, color=SUCCESS if reward_ready else TEXT_SECONDARY),
                    ft.Text(f"Total: {total}", size=SMALL_SIZE, color=TEXT_SECONDARY),
                ], spacing=16),
                progress_bar,
            ], spacing=6),
            padding=ft.padding.symmetric(horizontal=12, vertical=10),
            border_radius=10,
            bgcolor=ft.Colors.with_opacity(0.06, SUCCESS if reward_ready else PRIMARY),
            border=ft.border.all(1, ft.Colors.with_opacity(0.2, SUCCESS if reward_ready else DIVIDER_COLOR)),
        )

    def _loyalty_build(search: str = "") -> list:
        customers = _loyalty_load(search)
        ready_count = sum(1 for c in customers if c["reward_ready"])
        controls = []

        # Header resumen
        controls.append(ft.Row([
            ft.Column([
                ft.Text(f"{len(customers)} clientes", size=SMALL_SIZE, color=TEXT_SECONDARY),
                ft.Text(f"{ready_count} con recompensa lista",
                        size=SMALL_SIZE, color=SUCCESS if ready_count else TEXT_SECONDARY,
                        weight=ft.FontWeight.W_600 if ready_count else ft.FontWeight.NORMAL),
            ], spacing=2, expand=True),
            ft.Text(f"Meta: {LOYALTY_PURCHASES_FOR_REWARD} compras",
                    size=SMALL_SIZE, color=TEXT_SECONDARY, italic=True),
        ]))

        if customers:
            for c in customers:
                controls.append(_customer_card(c))
        else:
            controls.append(ft.Text(
                "No hay clientes fidelizados aún." if not search else "Sin resultados.",
                size=SMALL_SIZE, color=TEXT_SECONDARY, italic=True,
            ))
        return controls

    def _on_loyalty_search(e):
        _loyalty_refresh(loyalty_search_ref.current.value)

    loyalty_section = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.LOYALTY, color=PRIMARY_DARK, size=20),
                ft.Text("Clientes Fidelizados", size=BODY_SIZE,
                        weight=ft.FontWeight.W_600, color=TEXT_PRIMARY, expand=True),
                ft.IconButton(
                    icon=ft.Icons.PERSON_ADD, icon_color=PRIMARY, icon_size=20,
                    tooltip="Agregar cliente",
                    on_click=lambda e: _open_add_customer_dialog(),
                ),
            ], spacing=8),
            ft.TextField(
                ref=loyalty_search_ref,
                hint_text="Buscar por nombre o correo…",
                prefix_icon=ft.Icons.SEARCH,
                border_color=PRIMARY,
                text_size=BODY_SIZE,
                on_change=_on_loyalty_search,
                dense=True,
            ),
            ft.Divider(height=1, color=DIVIDER_COLOR),
            ft.Column(_loyalty_build(), ref=loyalty_area, spacing=8,
                      scroll=ft.ScrollMode.AUTO),
        ], spacing=10),
        padding=16, border_radius=12, bgcolor=SURFACE,
        shadow=ft.BoxShadow(spread_radius=0, blur_radius=8,
                            color=ft.Colors.with_opacity(0.1, "black"), offset=ft.Offset(0, 2)),
    )

    # ── Layout principal ─────────────────────────────────────────

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
        ft.Column([
            ft.Column(initial_content, ref=sales_area, spacing=16),
            ft.Container(height=8),
            loyalty_section,
        ], spacing=0, scroll=ft.ScrollMode.AUTO, expand=True),
    ], expand=True)

    return ft.Container(
        content=responsive_layout(page, main_col, cal),
        padding=r_padding(page), expand=True,
    )
