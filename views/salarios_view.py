import flet as ft
from datetime import date, datetime
from database.db import get_session
from database.models import User, UserRole, ClockRecord, MonthlySalaryPayment
from components.confirm_dialog import confirm_delete_dialog
from components.date_field import make_date_field
from utils.responsive import r_padding, r_font_title, r_dialog_width, is_phone
from utils.toast import show_toast
from utils.audit import log_action
from assets.styles import (
    PRIMARY, PRIMARY_DARK, PRIMARY_LIGHT, SURFACE, SUCCESS, ERROR, ACCENT,
    TEXT_PRIMARY, TEXT_SECONDARY, FONT_FAMILY, SUBTITLE_SIZE, BODY_SIZE, SMALL_SIZE, DIVIDER_COLOR,
)

MESES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


def salarios_view(page: ft.Page, user: User):
    """Vista de Salarios Mensuales: marca/desmarca pagos por empleado."""

    # Estado: mes seleccionado (siempre día 1)
    today = date.today()
    selected_month = [today.replace(day=1)]

    content_area = ft.Ref[ft.Column]()
    month_title = ft.Ref[ft.Text]()

    # ── helpers de datos ──

    def _calc_hours(worker_id: int, first: date, nxt: date, session) -> float:
        records = session.query(ClockRecord).filter(
            ClockRecord.user_id == worker_id,
            ClockRecord.clock_in >= first.isoformat(),
            ClockRecord.clock_in < nxt.isoformat(),
            ClockRecord.clock_out.isnot(None),
        ).all()
        return round(sum(r.hours_worked for r in records), 2)

    def _next_month(d: date) -> date:
        if d.month == 12:
            return d.replace(year=d.year + 1, month=1, day=1)
        return d.replace(month=d.month + 1, day=1)

    def _load_data(first: date):
        nxt = _next_month(first)
        session = get_session()
        try:
            workers = (
                session.query(User)
                .filter_by(is_active=True, role=UserRole.WORKER)
                .order_by(User.name)
                .all()
            )
            result = []
            for w in workers:
                hours = _calc_hours(w.id, first, nxt, session)
                earned = round(hours * w.hourly_rate, 2)
                payment = session.query(MonthlySalaryPayment).filter_by(
                    user_id=w.id, month=first
                ).first()
                result.append({
                    "worker_id": w.id,
                    "name": w.name,
                    "hours": hours,
                    "rate": w.hourly_rate,
                    "earned": earned,
                    "payment_id": payment.id if payment else None,
                    "is_paid": payment.is_paid if payment else False,
                    "paid_date": payment.paid_date if payment else None,
                    "amount_paid": payment.amount if payment else 0.0,
                    "notes": payment.notes if payment else "",
                })
            return result
        finally:
            session.close()

    # ── diálogo para registrar / editar pago ──

    def _open_pay_dialog(wdata: dict, month_first: date):
        ph = is_phone(page)
        mes_label = f"{MESES_ES[month_first.month - 1]} {month_first.year}"

        amount_field = ft.TextField(
            label="Monto pagado ($)",
            value=f"{wdata['earned']:.2f}",
            expand=ph,
            width=r_dialog_width(page) - 48 if not ph else None,
            border_color=PRIMARY,
            text_size=BODY_SIZE,
            prefix_icon=ft.Icons.ATTACH_MONEY,
            autofocus=True,
        )
        paid_date_field = make_date_field(
            "Fecha de pago",
            value=date.today().strftime("%d/%m/%Y"),
            expand=ph,
            width=r_dialog_width(page) - 48 if not ph else None,
            border_color=PRIMARY,
            text_size=BODY_SIZE,
        )
        notes_field = ft.TextField(
            label="Notas (opcional)",
            expand=ph,
            width=r_dialog_width(page) - 48 if not ph else None,
            border_color=PRIMARY,
            text_size=BODY_SIZE,
            multiline=True,
            min_lines=2,
            max_lines=3,
        )
        error_text = ft.Text("", color=ERROR, size=SMALL_SIZE)

        def _save(e):
            try:
                amt = float(amount_field.value or "0")
                if amt <= 0:
                    error_text.value = "El monto debe ser mayor a 0."
                    error_text.update()
                    return
                pd = datetime.strptime(paid_date_field.value.strip(), "%d/%m/%Y").date()
            except ValueError:
                error_text.value = "Fecha inválida. Usa el formato DD/MM/YYYY."
                error_text.update()
                return

            session = get_session()
            try:
                nxt = _next_month(month_first)
                if wdata["payment_id"]:
                    rec = session.query(MonthlySalaryPayment).get(wdata["payment_id"])
                    rec.amount = amt
                    rec.paid_date = pd
                    rec.is_paid = True
                    rec.notes = notes_field.value.strip()
                else:
                    hrs = _calc_hours(wdata["worker_id"], month_first, nxt, session)
                    w_obj = session.query(User).get(wdata["worker_id"])
                    rec = MonthlySalaryPayment(
                        user_id=wdata["worker_id"],
                        month=month_first,
                        hours_worked=hrs,
                        hourly_rate=w_obj.hourly_rate,
                        amount=amt,
                        is_paid=True,
                        paid_date=pd,
                        notes=notes_field.value.strip(),
                    )
                    session.add(rec)
                session.commit()
                log_action(user.id, "UPDATE" if wdata["payment_id"] else "CREATE",
                           "MonthlySalaryPayment", None,
                           f"{wdata['name']} — {mes_label} — ${amt:.2f}")
            finally:
                session.close()

            page.pop_dialog()
            show_toast(page, f"Pago de {wdata['name']} ({mes_label}) registrado", is_success=True)
            _refresh()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(ft.Icons.PAYMENTS, color=PRIMARY_DARK, size=24),
                ft.Text(f"Registrar Pago — {wdata['name']}", size=SUBTITLE_SIZE,
                        weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
            ], spacing=8),
            content=ft.Container(
                content=ft.Column([
                    ft.Text(f"Mes: {mes_label}", size=BODY_SIZE, color=TEXT_SECONDARY),
                    ft.Text(
                        f"Devengado: ${wdata['earned']:,.2f}  ({wdata['hours']:.1f}h × ${wdata['rate']:.0f}/h)",
                        size=SMALL_SIZE, color=TEXT_SECONDARY,
                    ),
                    ft.Divider(height=1),
                    amount_field,
                    paid_date_field,
                    notes_field,
                    error_text,
                ], spacing=10, tight=True),
                width=r_dialog_width(page),
            ),
            actions=[
                ft.TextButton(
                    content=ft.Text("Cancelar"),
                    on_click=lambda e: page.pop_dialog(),
                ),
                ft.ElevatedButton(
                    content=ft.Text("Guardar Pago", color="white"),
                    bgcolor=SUCCESS,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                    on_click=_save,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(dlg)

    # ── desmarcar pago ──

    def _unpay(wdata: dict, month_first: date):
        mes_label = f"{MESES_ES[month_first.month - 1]} {month_first.year}"

        def _do():
            session = get_session()
            try:
                rec = session.query(MonthlySalaryPayment).filter_by(
                    user_id=wdata["worker_id"], month=month_first
                ).first()
                if rec:
                    rec.is_paid = False
                    rec.paid_date = None
                    session.commit()
                    log_action(user.id, "UPDATE", "MonthlySalaryPayment", rec.id,
                               f"{wdata['name']} — {mes_label} — desmarcado")
            finally:
                session.close()
            show_toast(page, f"Pago de {wdata['name']} desmarcado", is_success=False)
            _refresh()

        confirm_delete_dialog(
            page,
            "Desmarcar Pago",
            f"¿Marcar el salario de {wdata['name']} ({mes_label}) como NO pagado?",
            _do,
        )

    # ── construir tarjeta de empleado ──

    def _worker_card(wdata: dict, month_first: date, is_admin: bool) -> ft.Container:
        paid = wdata["is_paid"]

        status_badge = ft.Container(
            content=ft.Text(
                "PAGADO" if paid else "PENDIENTE",
                size=SMALL_SIZE, color="white", weight=ft.FontWeight.BOLD,
            ),
            bgcolor=SUCCESS if paid else ACCENT,
            border_radius=6,
            padding=ft.padding.symmetric(horizontal=8, vertical=3),
        )

        if paid:
            detail_text = ft.Text(
                f"Pagado el {wdata['paid_date'].strftime('%d/%m/%Y')} — ${wdata['amount_paid']:,.2f}",
                size=SMALL_SIZE, color=TEXT_SECONDARY,
            )
        else:
            detail_text = ft.Text(
                "Pendiente de pago",
                size=SMALL_SIZE, color=ACCENT, italic=True,
            )

        # Botones solo para admin
        if is_admin:
            if paid:
                action_btn = ft.Row([
                    ft.IconButton(
                        icon=ft.Icons.EDIT,
                        icon_color=PRIMARY,
                        icon_size=18,
                        tooltip="Editar pago",
                        on_click=lambda e, w=wdata, m=month_first: _open_pay_dialog(w, m),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.UNDO,
                        icon_color=ACCENT,
                        icon_size=18,
                        tooltip="Desmarcar como pagado",
                        on_click=lambda e, w=wdata, m=month_first: _unpay(w, m),
                    ),
                ], spacing=0)
            else:
                action_btn = ft.IconButton(
                    icon=ft.Icons.CHECK_CIRCLE_OUTLINE,
                    icon_color=SUCCESS,
                    icon_size=22,
                    tooltip="Marcar como pagado",
                    on_click=lambda e, w=wdata, m=month_first: _open_pay_dialog(w, m),
                )
        else:
            action_btn = ft.Container()

        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.PERSON, color=PRIMARY, size=20),
                    ft.Text(
                        wdata["name"],
                        size=BODY_SIZE,
                        weight=ft.FontWeight.W_600,
                        color=TEXT_PRIMARY,
                        expand=True,
                    ),
                    status_badge,
                    action_btn,
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                ft.Row([
                    ft.Text(
                        f"{wdata['hours']:.1f} horas × ${wdata['rate']:.0f}/h  =  ${wdata['earned']:,.2f} devengado",
                        size=SMALL_SIZE,
                        color=TEXT_SECONDARY,
                        expand=True,
                    ),
                    detail_text,
                ], spacing=8),
            ], spacing=6),
            padding=ft.padding.symmetric(horizontal=14, vertical=10),
            border_radius=10,
            bgcolor=ft.Colors.with_opacity(0.05, SUCCESS if paid else ACCENT),
            border=ft.border.all(1, ft.Colors.with_opacity(0.15, SUCCESS if paid else ACCENT)),
        )

    # ── construir contenido del mes ──

    def _build_content(month_first: date) -> list:
        salary_data = _load_data(month_first)
        is_admin = user.role == UserRole.ADMIN
        mes_label = f"{MESES_ES[month_first.month - 1]} {month_first.year}"

        total_earned = sum(w["earned"] for w in salary_data)
        total_paid = sum(w["amount_paid"] for w in salary_data if w["is_paid"])
        pending = total_earned - total_paid
        count_paid = sum(1 for w in salary_data if w["is_paid"])
        count_total = len(salary_data)

        controls = []

        # ── Resumen mensual ──
        summary = ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Text("Devengado total", size=SMALL_SIZE, color=TEXT_SECONDARY),
                    ft.Text(f"${total_earned:,.2f}", size=20,
                            weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
                ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
                ft.VerticalDivider(width=1, color=DIVIDER_COLOR),
                ft.Column([
                    ft.Text("Ya pagado", size=SMALL_SIZE, color=TEXT_SECONDARY),
                    ft.Text(f"${total_paid:,.2f}", size=20,
                            weight=ft.FontWeight.BOLD, color=SUCCESS),
                ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
                ft.VerticalDivider(width=1, color=DIVIDER_COLOR),
                ft.Column([
                    ft.Text("Pendiente", size=SMALL_SIZE, color=TEXT_SECONDARY),
                    ft.Text(f"${pending:,.2f}", size=20,
                            weight=ft.FontWeight.BOLD, color=ACCENT if pending > 0 else TEXT_SECONDARY),
                ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
            ], alignment=ft.MainAxisAlignment.SPACE_EVENLY),
            padding=16,
            border_radius=12,
            bgcolor=SURFACE,
            shadow=ft.BoxShadow(
                spread_radius=0, blur_radius=8,
                color=ft.Colors.with_opacity(0.1, "black"), offset=ft.Offset(0, 2),
            ),
        )
        controls.append(summary)

        # ── Progreso de pagos ──
        progress_row = ft.Row([
            ft.Text(
                f"{count_paid} de {count_total} empleados pagados",
                size=SMALL_SIZE, color=TEXT_SECONDARY,
            ),
        ])
        controls.append(progress_row)

        # ── Tarjetas por empleado ──
        if salary_data:
            for wdata in salary_data:
                controls.append(_worker_card(wdata, month_first, is_admin))
        else:
            controls.append(ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.PEOPLE_OUTLINE, size=48, color=TEXT_SECONDARY),
                    ft.Text("No hay trabajadores activos registrados.",
                            size=BODY_SIZE, color=TEXT_SECONDARY, italic=True,
                            text_align=ft.TextAlign.CENTER),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                padding=32,
                alignment=ft.Alignment(0, 0),
            ))

        return controls

    def _refresh():
        month_first = selected_month[0]
        mes_label = f"{MESES_ES[month_first.month - 1]} {month_first.year}"
        month_title.current.value = f"Salarios — {mes_label}"
        month_title.current.update()
        content_area.current.controls.clear()
        content_area.current.controls.extend(_build_content(month_first))
        content_area.current.update()

    # ── navegación de meses ──

    def _prev_month(e):
        m = selected_month[0]
        if m.month == 1:
            selected_month[0] = m.replace(year=m.year - 1, month=12, day=1)
        else:
            selected_month[0] = m.replace(month=m.month - 1, day=1)
        _refresh()

    def _next_month_nav(e):
        selected_month[0] = _next_month(selected_month[0])
        _refresh()

    # ── UI inicial ──

    month_first = selected_month[0]
    mes_label = f"{MESES_ES[month_first.month - 1]} {month_first.year}"
    initial_content = _build_content(month_first)

    month_nav = ft.Row([
        ft.IconButton(
            icon=ft.Icons.CHEVRON_LEFT,
            icon_color=PRIMARY,
            icon_size=24,
            tooltip="Mes anterior",
            on_click=_prev_month,
        ),
        ft.Text(
            f"Salarios — {mes_label}",
            ref=month_title,
            size=BODY_SIZE,
            weight=ft.FontWeight.W_600,
            color=PRIMARY_DARK,
        ),
        ft.IconButton(
            icon=ft.Icons.CHEVRON_RIGHT,
            icon_color=PRIMARY,
            icon_size=24,
            tooltip="Mes siguiente",
            on_click=_next_month_nav,
        ),
    ], alignment=ft.MainAxisAlignment.CENTER, spacing=4)

    main_col = ft.Column([
        ft.Row([
            ft.Column([
                ft.Text("Salarios", size=r_font_title(page),
                        weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
                ft.Text("Salarios mensuales por empleado", size=BODY_SIZE, color=TEXT_SECONDARY),
            ], spacing=4, expand=True),
        ]),
        ft.Container(height=4),
        month_nav,
        ft.Container(height=4),
        ft.Column(
            initial_content,
            ref=content_area,
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        ),
    ], expand=True)

    return ft.Container(
        content=main_col,
        padding=r_padding(page),
        expand=True,
    )
