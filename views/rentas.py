import flet as ft
from datetime import date
from database.db import get_session
from database.models import Rent, RentStatus, RentTenant, UserRole
from components.calendar_picker import calendar_picker
from components.confirm_dialog import confirm_delete_dialog
from utils.responsive import is_mobile, responsive_layout, r_padding, r_font_title, r_calendar_width, r_dialog_width, r_field_width, is_phone
from utils.toast import show_toast
from assets.styles import (
    PRIMARY, PRIMARY_DARK, SURFACE, SUCCESS, ERROR, ACCENT,
    TEXT_PRIMARY, TEXT_SECONDARY, TITLE_SIZE, SUBTITLE_SIZE, BODY_SIZE, SMALL_SIZE, DIVIDER_COLOR,
)

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
         "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def rentas_view(page: ft.Page, user):
    """Módulo de Rentas: crear, cobrar, editar y eliminar rentas."""

    selected_date = date.today()
    content_area = ft.Ref[ft.Column]()
    subtitle_ref = ft.Ref[ft.Text]()

    is_admin = user.role == UserRole.ADMIN

    # ── helpers ──

    def _load_tenants() -> list[str]:
        session = get_session()
        try:
            tenants = session.query(RentTenant).filter_by(is_active=True).order_by(RentTenant.name).all()
            return [t.name for t in tenants]
        finally:
            session.close()

    def _build_subtitle() -> str:
        tenants = _load_tenants()
        if tenants:
            return ", ".join(tenants)
        return "Sin inquilinos registrados"

    def _load_rents(d: date):
        session = get_session()
        try:
            first_of_month = d.replace(day=1)
            rents = session.query(Rent).filter(Rent.month == first_of_month).order_by(Rent.tenant).all()
            result = []
            for r in rents:
                result.append({
                    "id": r.id, "tenant": r.tenant, "month": r.month,
                    "amount": r.amount, "status": r.status,
                    "paid_date": r.paid_date,
                })
            return result
        finally:
            session.close()

    def _refresh():
        content_area.current.controls.clear()
        content_area.current.controls.extend(_build_content(selected_date))
        content_area.current.update()
        if subtitle_ref.current:
            subtitle_ref.current.value = _build_subtitle()
            subtitle_ref.current.update()

    # ── diálogo de gestión de inquilinos (solo admin) ──

    def _manage_tenants_dialog():
        ph = is_phone(page)
        tenants_col = ft.Ref[ft.Column]()

        def _load_tenant_rows():
            session = get_session()
            try:
                tenants = session.query(RentTenant).order_by(RentTenant.name).all()
                rows = []
                for t in tenants:
                    active = t.is_active

                    def _toggle(e, tid=t.id, was_active=active):
                        s = get_session()
                        try:
                            rec = s.query(RentTenant).get(tid)
                            rec.is_active = not was_active
                            s.commit()
                        finally:
                            s.close()
                        _reload_rows()

                    def _delete_tenant(e, tid=t.id, tname=t.name):
                        def _do():
                            s = get_session()
                            try:
                                s.query(Rent).filter_by(tenant=tname)
                                rec = s.query(RentTenant).get(tid)
                                if rec:
                                    s.delete(rec)
                                    s.commit()
                            finally:
                                s.close()
                            _reload_rows()
                        confirm_delete_dialog(
                            page,
                            "Eliminar Inquilino",
                            f"¿Eliminar a '{tname}'? Sus rentas registradas no se borran.",
                            _do,
                        )

                    rows.append(ft.Row([
                        ft.Text(
                            t.name, size=BODY_SIZE, color=TEXT_PRIMARY, expand=True,
                            color_scheme_key=ft.ColorSchemeKey.ON_SURFACE if active else None,
                            opacity=1.0 if active else 0.45,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.TOGGLE_ON if active else ft.Icons.TOGGLE_OFF,
                            icon_color=SUCCESS if active else TEXT_SECONDARY,
                            icon_size=20,
                            tooltip="Desactivar" if active else "Reactivar",
                            on_click=_toggle,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.DELETE_OUTLINE,
                            icon_color=ERROR,
                            icon_size=18,
                            tooltip="Eliminar",
                            on_click=_delete_tenant,
                        ),
                    ], vertical_alignment=ft.CrossAxisAlignment.CENTER))
                return rows
            finally:
                session.close()

        def _reload_rows():
            tenants_col.current.controls.clear()
            tenants_col.current.controls.extend(_load_tenant_rows())
            tenants_col.current.update()
            _refresh()

        new_name = ft.TextField(
            label="Nombre del inquilino / empresa",
            expand=True,
            border_color=PRIMARY,
            text_size=BODY_SIZE,
            autofocus=True,
        )
        add_error = ft.Text("", color=ERROR, size=SMALL_SIZE)

        def _add_tenant(e):
            name = new_name.value.strip()
            if not name:
                add_error.value = "Escribe un nombre."
                add_error.update()
                return
            session = get_session()
            try:
                existing = session.query(RentTenant).filter(
                    RentTenant.name.ilike(name)
                ).first()
                if existing:
                    if not existing.is_active:
                        existing.is_active = True
                        session.commit()
                        show_toast(page, f"'{existing.name}' reactivado", is_success=True)
                    else:
                        add_error.value = f"'{name}' ya existe."
                        add_error.update()
                        return
                else:
                    session.add(RentTenant(name=name))
                    session.commit()
                    show_toast(page, f"Inquilino '{name}' agregado", is_success=True)
            finally:
                session.close()
            new_name.value = ""
            add_error.value = ""
            _reload_rows()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(ft.Icons.PEOPLE_ALT, color=PRIMARY_DARK, size=24),
                ft.Text("Gestionar Inquilinos", size=SUBTITLE_SIZE,
                        weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
            ], spacing=8),
            content=ft.Container(
                content=ft.Column([
                    ft.Text("Agrega personas o empresas a las que cobrar renta:",
                            size=SMALL_SIZE, color=TEXT_SECONDARY),
                    ft.Row([new_name,
                            ft.IconButton(
                                icon=ft.Icons.ADD_CIRCLE,
                                icon_color=SUCCESS,
                                icon_size=26,
                                tooltip="Agregar",
                                on_click=_add_tenant,
                            )], spacing=4),
                    add_error,
                    ft.Divider(height=1, color=DIVIDER_COLOR),
                    ft.Column(
                        _load_tenant_rows(),
                        ref=tenants_col,
                        spacing=4,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                ], spacing=10, tight=True),
                width=r_dialog_width(page, 380),
                height=350,
            ),
            actions=[
                ft.TextButton(
                    content=ft.Text("Cerrar"),
                    on_click=lambda e: page.pop_dialog(),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(dlg)

    def _add_rent_dialog():
        ph = is_phone(page)
        tenant_dd = ft.Dropdown(
            label="Inquilino", width=r_field_width(page, 200), expand=ph,
            options=[ft.dropdown.Option(t) for t in TENANTS],
            value=TENANTS[0], border_color=PRIMARY, text_size=BODY_SIZE,
        )
        amount_field = ft.TextField(
            label="Monto ($)", width=r_field_width(page, 150), expand=ph, text_size=BODY_SIZE, border_color=PRIMARY,
            prefix_icon=ft.Icons.ATTACH_MONEY,
            input_filter=ft.InputFilter(regex_string=r"[0-9.]", allow=True),
            autofocus=True,
        )
        month_dd = ft.Dropdown(
            label="Mes", width=r_field_width(page, 150), expand=ph,
            options=[ft.dropdown.Option(key=str(i + 1), text=MESES[i]) for i in range(12)],
            value=str(selected_date.month), border_color=PRIMARY, text_size=BODY_SIZE,
        )
        year_field = ft.TextField(
            label="Año", width=r_field_width(page, 100), expand=ph, text_size=BODY_SIZE, border_color=PRIMARY,
            value=str(selected_date.year),
            input_filter=ft.InputFilter(regex_string=r"[0-9]", allow=True),
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

            m = int(month_dd.value)
            y = int(year_field.value or selected_date.year)
            month_date = date(y, m, 1)

            session = get_session()
            try:
                rent = Rent(tenant=tenant_dd.value, month=month_date, amount=amount)
                session.add(rent)
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
            title=ft.Text("Nueva Renta", size=SUBTITLE_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
            content=ft.Container(
                content=ft.Column([tenant_dd, amount_field, ft.Row([month_dd, year_field], spacing=12), status_text], spacing=14),
                width=r_dialog_width(page, 380), height=None if ph else 230,
            ),
            actions=[
                ft.TextButton(content=ft.Text("Cancelar"), on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton(content=ft.Text("Guardar", color="white"), bgcolor=SUCCESS,
                                  style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)), on_click=_save),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(dlg)

    def _mark_paid(rent_id: int):
        session = get_session()
        try:
            r = session.query(Rent).get(rent_id)
            if r:
                r.status = RentStatus.PAID
                r.paid_date = date.today()
                session.commit()
        finally:
            session.close()
        _refresh()

    def _mark_unpaid(rent_id: int):
        session = get_session()
        try:
            r = session.query(Rent).get(rent_id)
            if r:
                r.status = RentStatus.PENDING
                r.paid_date = None
                session.commit()
        finally:
            session.close()
        _refresh()

    def _delete_rent(rent_id: int, tenant: str):
        def _do():
            session = get_session()
            try:
                r = session.query(Rent).get(rent_id)
                if r:
                    session.delete(r)
                    session.commit()
            finally:
                session.close()
            _refresh()
        confirm_delete_dialog(page, "Eliminar Renta", f"¿Eliminar la renta de {tenant}?", _do)

    # ── build UI ──

    def _rent_card(r):
        is_pending = r["status"] == RentStatus.PENDING
        status_color = ERROR if is_pending else SUCCESS
        status_label = "Pendiente" if is_pending else (
            f"Cobrado el {r['paid_date'].strftime('%d/%m/%Y')}" if r["paid_date"] else "Cobrado"
        )
        mes_label = f"{MESES[r['month'].month - 1]} {r['month'].year}"

        action_btn = ft.ElevatedButton(
            content=ft.Text("Marcar Cobrado" if is_pending else "Desmarcar", color="white"),
            bgcolor=SUCCESS if is_pending else TEXT_SECONDARY,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6),
                                 padding=ft.padding.symmetric(horizontal=10, vertical=6)),
            on_click=lambda e, rid=r["id"]: _mark_paid(rid) if is_pending else _mark_unpaid(rid),
        )

        return ft.Container(
            content=ft.Row([
                ft.Container(
                    content=ft.Text(r["tenant"][0].upper(), size=16, color="white", weight=ft.FontWeight.BOLD),
                    width=40, height=40, border_radius=20,
                    bgcolor=PRIMARY, alignment=ft.Alignment(0, 0),
                ),
                ft.Column([
                    ft.Text(f"Renta de {r['tenant']}", size=BODY_SIZE, weight=ft.FontWeight.W_500, color=TEXT_PRIMARY),
                    ft.Text(f"Mes: {mes_label}", size=SMALL_SIZE, color=TEXT_SECONDARY),
                ], spacing=2, expand=True),
                ft.Column([
                    ft.Text(f"${r['amount']:,.2f}", size=BODY_SIZE, weight=ft.FontWeight.BOLD, color=status_color),
                    ft.Text(status_label, size=SMALL_SIZE, color=status_color),
                ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.END),
                action_btn,
                ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=16, icon_color=ERROR, tooltip="Eliminar",
                              on_click=lambda e, rid=r["id"], t=r["tenant"]: _delete_rent(rid, t)),
            ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=14, border_radius=10, bgcolor=SURFACE,
            border=ft.border.all(1, DIVIDER_COLOR),
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

    def _build_content(d: date):
        rents = _load_rents(d)
        pending = [r for r in rents if r["status"] == RentStatus.PENDING]
        paid = [r for r in rents if r["status"] == RentStatus.PAID]

        mes_label = f"{MESES[d.month - 1]} {d.year}"

        pending_items = [_rent_card(r) for r in pending] if pending else [
            ft.Text("Sin rentas pendientes este mes", size=SMALL_SIZE, color=TEXT_SECONDARY, italic=True)
        ]
        paid_items = [_rent_card(r) for r in paid] if paid else [
            ft.Text("Sin rentas cobradas este mes", size=SMALL_SIZE, color=TEXT_SECONDARY, italic=True)
        ]

        total_pending = sum(r["amount"] for r in pending)
        total_paid = sum(r["amount"] for r in paid)

        summary = ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Text("Pendiente", size=SMALL_SIZE, color=TEXT_SECONDARY),
                    ft.Text(f"${total_pending:,.2f}", size=SUBTITLE_SIZE, weight=ft.FontWeight.BOLD, color=ERROR),
                ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
                ft.Column([
                    ft.Text("Cobrado", size=SMALL_SIZE, color=TEXT_SECONDARY),
                    ft.Text(f"${total_paid:,.2f}", size=SUBTITLE_SIZE, weight=ft.FontWeight.BOLD, color=SUCCESS),
                ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
            ], alignment=ft.MainAxisAlignment.SPACE_AROUND),
            padding=16, border_radius=12, bgcolor=SURFACE,
            shadow=ft.BoxShadow(spread_radius=0, blur_radius=8,
                                color=ft.Colors.with_opacity(0.1, "black"), offset=ft.Offset(0, 2)),
        )

        return [
            summary,
            _section(f"Pendientes ({len(pending)}) — {mes_label}", ft.Icons.PENDING_ACTIONS, pending_items),
            _section(f"Cobrados ({len(paid)}) — {mes_label}", ft.Icons.CHECK_CIRCLE, paid_items),
        ]

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
                ft.Text("Rentas", size=r_font_title(page), weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
                ft.Text(_build_subtitle(), ref=subtitle_ref, size=BODY_SIZE, color=TEXT_SECONDARY),
            ], spacing=4, expand=True),
            ft.Row([
                ft.ElevatedButton(
                    content=ft.Row([ft.Icon(ft.Icons.ADD, size=16, color="white"),
                                    ft.Text("Nueva Renta", size=SMALL_SIZE, color="white")], spacing=4),
                    bgcolor=SUCCESS, on_click=lambda e: _add_rent_dialog(),
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6),
                                         padding=ft.padding.symmetric(horizontal=12, vertical=8)),
                ),
            ] + ([
                ft.IconButton(
                    icon=ft.Icons.MANAGE_ACCOUNTS,
                    icon_color=PRIMARY,
                    icon_size=22,
                    tooltip="Gestionar inquilinos",
                    on_click=lambda e: _manage_tenants_dialog(),
                ),
            ] if is_admin else []), spacing=8),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ft.Container(height=8),
        ft.Column(initial_content, ref=content_area, spacing=16, scroll=ft.ScrollMode.AUTO, expand=True),
    ], expand=True)

    return ft.Container(
        content=responsive_layout(page, main_col, cal),
        padding=r_padding(page), expand=True,
    )
