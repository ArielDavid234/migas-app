import flet as ft
from datetime import date, timedelta, datetime
from database.db import get_session
from database.models import User, UserRole, ClockRecord, Sale, Expense, ShiftType, Schedule, MonthlySalaryPayment
from sqlalchemy import func
from components.calendar_picker import calendar_picker
from components.sale_form import sale_form_dialog
from components.expense_form import expense_form_dialog
from components.confirm_dialog import confirm_delete_dialog
from assets.styles import (
    PRIMARY, PRIMARY_DARK, PRIMARY_LIGHT, SURFACE, SUCCESS, ERROR, ACCENT,
    TEXT_PRIMARY, TEXT_SECONDARY, FONT_FAMILY, TITLE_SIZE, SUBTITLE_SIZE, BODY_SIZE, SMALL_SIZE, DIVIDER_COLOR,
)
from config import HOURLY_RATE
from utils.responsive import is_mobile, responsive_layout, r_padding, r_font_title, r_calendar_width, r_dialog_width, is_phone
from utils.toast import show_toast
from utils.export import export_sales_excel, export_expenses_excel, export_daily_summary_excel, export_shift_summary_excel
from utils.audit import log_action


def cuenta_view(page: ft.Page, user: User):
    """Módulo de Cuenta: ventas, gastos, salarios — con CRUD completo."""

    selected_date = date.today()
    content_area = ft.Ref[ft.Column]()

    # ── helpers ──

    def _load_day_data(d: date):
        session = get_session()
        try:
            # Ventas individuales del día
            sales = session.query(Sale).filter(Sale.date == d).order_by(Sale.created_at.desc()).all()
            sales_list = [
                {
                    "id": s.id,
                    "shift": s.shift,
                    "amount": s.amount,
                    "description": s.description or "",
                    "is_cafeteria": s.is_cafeteria,
                    "user_id": s.user_id,
                }
                for s in sales
            ]

            morning_total = sum(s["amount"] for s in sales_list if s["shift"] == ShiftType.MORNING and not s["is_cafeteria"])
            night_total = sum(s["amount"] for s in sales_list if s["shift"] == ShiftType.NIGHT and not s["is_cafeteria"])
            cafe_total = sum(s["amount"] for s in sales_list if s["is_cafeteria"])

            # Gastos individuales del día
            expenses = session.query(Expense).filter(Expense.date == d).order_by(Expense.created_at.desc()).all()
            expenses_list = [
                {
                    "id": ex.id,
                    "description": ex.description,
                    "amount": ex.amount,
                    "is_merchandise": ex.is_merchandise,
                }
                for ex in expenses
            ]
            total_expenses = sum(ex["amount"] for ex in expenses_list)

            # Resumen mensual
            first_of_month = d.replace(day=1)
            if d.month == 12:
                next_month = d.replace(year=d.year + 1, month=1, day=1)
            else:
                next_month = d.replace(month=d.month + 1, day=1)

            monthly_sales = session.query(func.coalesce(func.sum(Sale.amount), 0)).filter(
                Sale.date >= first_of_month, Sale.date < next_month
            ).scalar()
            monthly_expenses = session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
                Expense.date >= first_of_month, Expense.date < next_month
            ).scalar()

            # Salarios semanales
            weekday = d.weekday()
            week_start = d - timedelta(days=weekday)
            week_end = week_start + timedelta(days=6)

            workers = session.query(User).filter_by(is_active=True, role=UserRole.WORKER).all()
            salary_data = []
            for w in workers:
                records = session.query(ClockRecord).filter(
                    ClockRecord.user_id == w.id,
                    ClockRecord.clock_in >= week_start.isoformat(),
                    ClockRecord.clock_in < (week_end + timedelta(days=1)).isoformat(),
                    ClockRecord.clock_out.isnot(None),
                ).all()
                total_hours = sum(r.hours_worked for r in records)
                salary_data.append({
                    "name": w.name,
                    "hours": total_hours,
                    "rate": w.hourly_rate,
                    "total": total_hours * w.hourly_rate,
                })

            return {
                "sales_list": sales_list,
                "morning_total": morning_total,
                "night_total": night_total,
                "cafe_total": cafe_total,
                "total_day_sales": morning_total + night_total + cafe_total,
                "expenses_list": expenses_list,
                "total_expenses": total_expenses,
                "monthly_sales": monthly_sales,
                "monthly_expenses": monthly_expenses,
                "monthly_balance": monthly_sales - monthly_expenses,
                "salary_data": salary_data,
                "week_start": week_start,
                "week_end": week_end,
            }
        finally:
            session.close()

    def _section(title, icon, controls):
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row([ft.Icon(icon, color=PRIMARY_DARK, size=20),
                            ft.Text(title, size=BODY_SIZE, weight=ft.FontWeight.W_600, color=TEXT_PRIMARY)], spacing=8),
                    ft.Divider(height=1, color=DIVIDER_COLOR),
                    *controls,
                ],
                spacing=8,
            ),
            padding=16, border_radius=12, bgcolor=SURFACE,
            shadow=ft.BoxShadow(spread_radius=0, blur_radius=8,
                                color=ft.Colors.with_opacity(0.1, "black"), offset=ft.Offset(0, 2)),
        )

    def _row_info(label, value, color=TEXT_PRIMARY):
        return ft.Row([
            ft.Text(label, size=BODY_SIZE, color=TEXT_SECONDARY, expand=True),
            ft.Text(value, size=BODY_SIZE, weight=ft.FontWeight.BOLD, color=color),
        ])

    # ── CRUD callbacks ──

    def _delete_sale(sale_id: int):
        def _do():
            session = get_session()
            try:
                sale = session.query(Sale).get(sale_id)
                if sale:
                    log_action(user.id, "DELETE", "Sale", sale_id, f"${sale.amount:.2f}")
                    session.delete(sale)
                    session.commit()
            finally:
                session.close()
            _refresh()
        confirm_delete_dialog(page, "Eliminar Venta", "¿Seguro que deseas eliminar esta venta?", _do)

    def _edit_sale(sale_id: int):
        sale_form_dialog(page, user.id, on_saved=_refresh, sale_id=sale_id)

    def _delete_expense(expense_id: int):
        def _do():
            session = get_session()
            try:
                exp = session.query(Expense).get(expense_id)
                if exp:
                    log_action(user.id, "DELETE", "Expense", expense_id, f"${exp.amount:.2f} - {exp.description}")
                    session.delete(exp)
                    session.commit()
            finally:
                session.close()
            _refresh()
        confirm_delete_dialog(page, "Eliminar Gasto", "¿Seguro que deseas eliminar este gasto?", _do)

    def _edit_expense(expense_id: int):
        expense_form_dialog(page, on_saved=_refresh, expense_id=expense_id)

    # ── Salario mensual helpers ──

    MESES_ES = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    ]

    def _calc_monthly_hours(worker_id: int, first_of_month: date, next_month: date, session) -> float:
        """Horas trabajadas en el mes completo."""
        records = session.query(ClockRecord).filter(
            ClockRecord.user_id == worker_id,
            ClockRecord.clock_in >= first_of_month.isoformat(),
            ClockRecord.clock_in < next_month.isoformat(),
            ClockRecord.clock_out.isnot(None),
        ).all()
        return round(sum(r.hours_worked for r in records), 2)

    def _load_monthly_salary_data(d: date):
        """Devuelve lista de {worker, hours, rate, earned, payment_record} para el mes."""
        first = d.replace(day=1)
        if d.month == 12:
            nxt = d.replace(year=d.year + 1, month=1, day=1)
        else:
            nxt = d.replace(month=d.month + 1, day=1)

        session = get_session()
        try:
            workers = session.query(User).filter_by(is_active=True, role=UserRole.WORKER).order_by(User.name).all()
            result = []
            for w in workers:
                hours = _calc_monthly_hours(w.id, first, nxt, session)
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
            return result, first
        finally:
            session.close()

    def _open_pay_dialog(worker_name: str, worker_id: int, earned: float, month_date: date, payment_id=None):
        """Diálogo para registrar o editar el pago de salario mensual."""
        ph = is_phone(page)
        amount_field = ft.TextField(
            label="Monto pagado ($)",
            value=f"{earned:.2f}",
            width=r_dialog_width(page) - 48 if not ph else None,
            expand=ph,
            border_color=PRIMARY,
            text_size=BODY_SIZE,
            prefix_icon=ft.Icons.ATTACH_MONEY,
            autofocus=True,
        )
        paid_date_field = ft.TextField(
            label="Fecha de pago (DD/MM/YYYY)",
            value=date.today().strftime("%d/%m/%Y"),
            width=r_dialog_width(page) - 48 if not ph else None,
            expand=ph,
            border_color=PRIMARY,
            text_size=BODY_SIZE,
        )
        notes_field = ft.TextField(
            label="Notas (opcional)",
            width=r_dialog_width(page) - 48 if not ph else None,
            expand=ph,
            border_color=PRIMARY,
            text_size=BODY_SIZE,
            multiline=True,
            min_lines=2,
            max_lines=3,
        )
        error_text = ft.Text("", color=ERROR, size=SMALL_SIZE)

        mes_label = MESES_ES[month_date.month - 1]
        month_first = month_date.replace(day=1)

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
                if payment_id:
                    rec = session.query(MonthlySalaryPayment).get(payment_id)
                    rec.amount = amt
                    rec.paid_date = pd
                    rec.is_paid = True
                    rec.notes = notes_field.value.strip()
                else:
                    # Calcular horas trabajadas ese mes
                    if month_date.month == 12:
                        nxt = month_date.replace(year=month_date.year + 1, month=1, day=1)
                    else:
                        nxt = month_date.replace(month=month_date.month + 1, day=1)
                    hrs = _calc_monthly_hours(worker_id, month_first, nxt, session)
                    rec = MonthlySalaryPayment(
                        user_id=worker_id,
                        month=month_first,
                        hours_worked=hrs,
                        hourly_rate=session.query(User).get(worker_id).hourly_rate,
                        amount=amt,
                        is_paid=True,
                        paid_date=pd,
                        notes=notes_field.value.strip(),
                    )
                    session.add(rec)
                session.commit()
                log_action(user.id, "CREATE" if not payment_id else "UPDATE",
                           "MonthlySalaryPayment", None,
                           f"{worker_name} — {mes_label} — ${amt:.2f}")
            finally:
                session.close()

            page.pop_dialog()
            show_toast(page, f"Pago de {worker_name} ({mes_label}) registrado", is_success=True)
            _refresh()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(ft.Icons.PAYMENTS, color=PRIMARY_DARK, size=24),
                ft.Text(f"Pago — {worker_name}", size=SUBTITLE_SIZE,
                        weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
            ], spacing=8),
            content=ft.Container(
                content=ft.Column([
                    ft.Text(f"Mes: {mes_label} {month_date.year}", size=BODY_SIZE, color=TEXT_SECONDARY),
                    ft.Text(f"Monto sugerido: ${earned:,.2f}  ({_get_hours_for_month(worker_id, month_date):.1f}h × ${_get_rate(worker_id):.0f}/h)",
                            size=SMALL_SIZE, color=TEXT_SECONDARY),
                    ft.Divider(height=1),
                    amount_field,
                    paid_date_field,
                    notes_field,
                    error_text,
                ], spacing=10, tight=True),
                width=r_dialog_width(page),
            ),
            actions=[
                ft.TextButton(content=ft.Text("Cancelar"), on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton(
                    content=ft.Text("Registrar Pago", color="white"),
                    bgcolor=SUCCESS,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                    on_click=_save,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(dlg)

    def _get_hours_for_month(worker_id: int, month_date: date) -> float:
        first = month_date.replace(day=1)
        if month_date.month == 12:
            nxt = month_date.replace(year=month_date.year + 1, month=1, day=1)
        else:
            nxt = month_date.replace(month=month_date.month + 1, day=1)
        session = get_session()
        try:
            return _calc_monthly_hours(worker_id, first, nxt, session)
        finally:
            session.close()

    def _get_rate(worker_id: int) -> float:
        session = get_session()
        try:
            w = session.query(User).get(worker_id)
            return w.hourly_rate if w else 15.0
        finally:
            session.close()

    def _build_monthly_salary_section(d: date):
        """Tarjeta de salarios mensuales: horas, monto y estado de pago."""
        salary_list, first = _load_monthly_salary_data(d)
        mes_label = f"{MESES_ES[first.month - 1]} {first.year}"
        is_admin = user.role == UserRole.ADMIN

        rows = []
        total_earned = 0.0
        total_paid = 0.0

        for w in salary_list:
            total_earned += w["earned"]
            if w["is_paid"]:
                total_paid += w["amount_paid"]

            # Badge de estado
            if w["is_paid"]:
                badge = ft.Container(
                    content=ft.Text("PAGADO", size=SMALL_SIZE, color="white", weight=ft.FontWeight.BOLD),
                    bgcolor=SUCCESS, border_radius=6,
                    padding=ft.padding.symmetric(horizontal=8, vertical=3),
                )
                paid_info = ft.Text(
                    f"Pagado el {w['paid_date'].strftime('%d/%m/%Y')} — ${w['amount_paid']:,.2f}",
                    size=SMALL_SIZE, color=TEXT_SECONDARY,
                )
            else:
                badge = ft.Container(
                    content=ft.Text("PENDIENTE", size=SMALL_SIZE, color="white", weight=ft.FontWeight.BOLD),
                    bgcolor=ACCENT, border_radius=6,
                    padding=ft.padding.symmetric(horizontal=8, vertical=3),
                )
                paid_info = ft.Text(
                    f"Pendiente de pago",
                    size=SMALL_SIZE, color=ACCENT, italic=True,
                )

            # Botón de pago (solo admin)
            pay_btn = ft.IconButton(
                icon=ft.Icons.PAYMENT,
                icon_color=PRIMARY if not w["is_paid"] else TEXT_SECONDARY,
                icon_size=18,
                tooltip="Registrar pago" if not w["is_paid"] else "Editar pago",
                on_click=lambda e, ww=w: _open_pay_dialog(
                    ww["name"], ww["worker_id"], ww["earned"], d, ww["payment_id"]
                ),
            ) if is_admin else ft.Container()

            row = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Text(w["name"], size=BODY_SIZE, weight=ft.FontWeight.W_600,
                                color=TEXT_PRIMARY, expand=True),
                        badge,
                        pay_btn,
                    ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Row([
                        ft.Text(
                            f"{w['hours']:.1f}h × ${w['rate']:.0f}/h  =  ${w['earned']:,.2f} devengado",
                            size=SMALL_SIZE, color=TEXT_SECONDARY, expand=True,
                        ),
                        paid_info,
                    ]),
                ], spacing=4),
                padding=ft.padding.symmetric(horizontal=12, vertical=8),
                border_radius=8,
                bgcolor=ft.Colors.with_opacity(0.04, SUCCESS if w["is_paid"] else ACCENT),
            )
            rows.append(row)

        if not rows:
            rows.append(ft.Text("No hay trabajadores activos.", size=SMALL_SIZE,
                                color=TEXT_SECONDARY, italic=True))

        # Totales del mes
        rows.append(ft.Divider(height=1, color=DIVIDER_COLOR))
        rows.append(ft.Row([
            ft.Text("Total devengado en el mes:", size=BODY_SIZE, color=TEXT_SECONDARY, expand=True),
            ft.Text(f"${total_earned:,.2f}", size=BODY_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
        ]))
        rows.append(ft.Row([
            ft.Text("Total ya pagado:", size=BODY_SIZE, color=TEXT_SECONDARY, expand=True),
            ft.Text(f"${total_paid:,.2f}", size=BODY_SIZE, weight=ft.FontWeight.BOLD, color=SUCCESS),
        ]))
        pendiente = total_earned - total_paid
        if pendiente > 0:
            rows.append(ft.Row([
                ft.Text("Pendiente por pagar:", size=BODY_SIZE, color=TEXT_SECONDARY, expand=True),
                ft.Text(f"${pendiente:,.2f}", size=BODY_SIZE, weight=ft.FontWeight.BOLD, color=ACCENT),
            ]))

        return _section(f"Salarios Mensuales — {mes_label}", ft.Icons.ACCOUNT_BALANCE_WALLET, rows)

    # ── build UI sections ──

    def _sale_row(s):
        shift_label = "☀ Mañana" if s["shift"] == ShiftType.MORNING else "🌙 Noche"
        tag = "☕ Café" if s["is_cafeteria"] else shift_label
        desc = s["description"] if s["description"] else "—"

        return ft.Container(
            content=ft.Row([
                ft.Container(
                    content=ft.Text(tag, size=SMALL_SIZE, color="white", weight=ft.FontWeight.W_500),
                    bgcolor=ACCENT if s["is_cafeteria"] else (SUCCESS if s["shift"] == ShiftType.MORNING else PRIMARY),
                    border_radius=6,
                    padding=ft.padding.symmetric(horizontal=8, vertical=3),
                ),
                ft.Text(desc, size=BODY_SIZE, color=TEXT_SECONDARY, expand=True),
                ft.Text(f"${s['amount']:,.2f}", size=BODY_SIZE, weight=ft.FontWeight.BOLD, color=SUCCESS),
                ft.IconButton(ft.Icons.EDIT, icon_size=16, icon_color=PRIMARY, tooltip="Editar",
                              on_click=lambda e, sid=s["id"]: _edit_sale(sid)),
                ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=16, icon_color=ERROR, tooltip="Eliminar",
                              on_click=lambda e, sid=s["id"]: _delete_sale(sid)),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.symmetric(vertical=4),
        )

    def _expense_row(ex):
        tag = "📦 Mercancía" if ex["is_merchandise"] else "💰 Extra"

        return ft.Container(
            content=ft.Row([
                ft.Container(
                    content=ft.Text(tag, size=SMALL_SIZE, color="white", weight=ft.FontWeight.W_500),
                    bgcolor="#FF8F00" if ex["is_merchandise"] else "#78909C",
                    border_radius=6,
                    padding=ft.padding.symmetric(horizontal=8, vertical=3),
                ),
                ft.Text(ex["description"], size=BODY_SIZE, color=TEXT_SECONDARY, expand=True),
                ft.Text(f"${ex['amount']:,.2f}", size=BODY_SIZE, weight=ft.FontWeight.BOLD, color=ERROR),
                ft.IconButton(ft.Icons.EDIT, icon_size=16, icon_color=PRIMARY, tooltip="Editar",
                              on_click=lambda e, eid=ex["id"]: _edit_expense(eid)),
                ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=16, icon_color=ERROR, tooltip="Eliminar",
                              on_click=lambda e, eid=ex["id"]: _delete_expense(eid)),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.symmetric(vertical=4),
        )

    def _build_content(d: date):
        data = _load_day_data(d)

        # ── Ventas del día (lista individual + totales) ──
        sale_rows = [_sale_row(s) for s in data["sales_list"]]
        if not sale_rows:
            sale_rows = [ft.Text("Sin ventas registradas", size=SMALL_SIZE, color=TEXT_SECONDARY, italic=True)]
        sale_rows.append(ft.Divider(height=1, color=DIVIDER_COLOR))
        sale_rows.append(
            ft.Row([
                ft.Column([
                    ft.Text(f"☀ Mañana: ${data['morning_total']:,.2f}", size=SMALL_SIZE, color=SUCCESS),
                    ft.Text(f"🌙 Noche: ${data['night_total']:,.2f}", size=SMALL_SIZE, color=PRIMARY),
                    ft.Text(f"☕ Café: ${data['cafe_total']:,.2f}", size=SMALL_SIZE, color=ACCENT),
                ], spacing=2, expand=True),
                ft.Container(
                    content=ft.Text(f"Total: ${data['total_day_sales']:,.2f}", size=SUBTITLE_SIZE,
                                    weight=ft.FontWeight.BOLD, color=SUCCESS),
                    bgcolor=ft.Colors.with_opacity(0.08, SUCCESS),
                    border_radius=8,
                    padding=ft.padding.symmetric(horizontal=14, vertical=6),
                ),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        )

        sales_section = _section(
            f"Ventas — {d.strftime('%d/%m/%Y')}  ({len(data['sales_list'])} registros)",
            ft.Icons.TRENDING_UP, sale_rows,
        )

        # ── Gastos del día (lista individual + totales) ──
        exp_rows = [_expense_row(ex) for ex in data["expenses_list"]]
        if not exp_rows:
            exp_rows = [ft.Text("Sin gastos registrados", size=SMALL_SIZE, color=TEXT_SECONDARY, italic=True)]
        exp_rows.append(ft.Divider(height=1, color=DIVIDER_COLOR))
        exp_rows.append(_row_info("Total Gastos:", f"${data['total_expenses']:,.2f}", ERROR))

        expenses_section = _section(
            f"Gastos — {d.strftime('%d/%m/%Y')}  ({len(data['expenses_list'])} registros)",
            ft.Icons.MONEY_OFF, exp_rows,
        )

        # ── Resumen mensual ──
        bal_color = SUCCESS if data["monthly_balance"] >= 0 else ERROR
        sign = "+" if data["monthly_balance"] >= 0 else ""
        monthly_section = _section("Resumen del Mes", ft.Icons.CALENDAR_MONTH, [
            _row_info("Ventas del mes:", f"${data['monthly_sales']:,.2f}", SUCCESS),
            _row_info("Gastos del mes:", f"${data['monthly_expenses']:,.2f}", ERROR),
            ft.Divider(height=1, color=DIVIDER_COLOR),
            _row_info("Balance:", f"{sign}${data['monthly_balance']:,.2f}", bal_color),
            ft.Container(
                content=ft.Text(
                    "MES POSITIVO ✓" if data["monthly_balance"] >= 0 else "MES NEGATIVO ✗",
                    size=BODY_SIZE, weight=ft.FontWeight.BOLD, color=bal_color,
                ),
                bgcolor=ft.Colors.with_opacity(0.1, bal_color),
                border_radius=8, padding=ft.padding.symmetric(horizontal=12, vertical=6),
                alignment=ft.Alignment(0, 0),
            ),
        ])

        # ── Salarios semanales ──
        week_label = f"Semana: {data['week_start'].strftime('%d/%m')} — {data['week_end'].strftime('%d/%m/%Y')}"
        salary_rows = []
        total_salary = 0
        for s in data["salary_data"]:
            salary_rows.append(
                _row_info(f"{s['name']} — {s['hours']:.1f}h × ${s['rate']:.0f}", f"${s['total']:,.2f}", PRIMARY)
            )
            total_salary += s["total"]
        if not salary_rows:
            salary_rows.append(ft.Text("Sin registros de horas", size=SMALL_SIZE, color=TEXT_SECONDARY, italic=True))
        salary_rows.append(ft.Divider(height=1, color=DIVIDER_COLOR))
        salary_rows.append(_row_info("Total Salarios Semana:", f"${total_salary:,.2f}", PRIMARY_DARK))

        salary_section = _section(f"Salarios Semanales — {week_label}", ft.Icons.PAYMENTS, salary_rows)

        # ── Salarios mensuales (pagados / pendientes) ──
        monthly_salary_section = _build_monthly_salary_section(d)

        # ── Balance del día ──
        day_balance = data["total_day_sales"] - data["total_expenses"]
        db_color = SUCCESS if day_balance >= 0 else ERROR
        db_sign = "+" if day_balance >= 0 else ""
        balance_section = ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Text("Balance del Día", size=BODY_SIZE, color=TEXT_SECONDARY),
                    ft.Text(
                        f"{db_sign}${day_balance:,.2f}",
                        size=24, weight=ft.FontWeight.BOLD, color=db_color,
                    ),
                ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
                ft.Column([
                    ft.Text("Ventas", size=SMALL_SIZE, color=TEXT_SECONDARY),
                    ft.Text(f"${data['total_day_sales']:,.2f}", size=BODY_SIZE, weight=ft.FontWeight.BOLD, color=SUCCESS),
                ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Container(
                    ft.Text("−", size=20, color=TEXT_SECONDARY), padding=ft.padding.symmetric(horizontal=8),
                ),
                ft.Column([
                    ft.Text("Gastos", size=SMALL_SIZE, color=TEXT_SECONDARY),
                    ft.Text(f"${data['total_expenses']:,.2f}", size=BODY_SIZE, weight=ft.FontWeight.BOLD, color=ERROR),
                ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=20),
            padding=16, border_radius=12, bgcolor=SURFACE,
            shadow=ft.BoxShadow(spread_radius=0, blur_radius=8,
                                color=ft.Colors.with_opacity(0.1, "black"), offset=ft.Offset(0, 2)),
        )

        return [balance_section, sales_section, expenses_section, monthly_section, salary_section, monthly_salary_section]

    # ── navigation / refresh ──

    def _on_date_selected(d: date):
        nonlocal selected_date
        selected_date = d
        content_area.current.controls.clear()
        content_area.current.controls.extend(_build_content(d))
        content_area.current.update()

    def _refresh():
        content_area.current.controls.clear()
        content_area.current.controls.extend(_build_content(selected_date))
        content_area.current.update()

    def _add_sale(e):
        sale_form_dialog(page, user.id, on_saved=_refresh)

    def _add_expense(e):
        expense_form_dialog(page, on_saved=_refresh)

    _dl_picker = ft.FilePicker()
    page.services.append(_dl_picker)

    async def _export_excel(e):
        try:
            import os
            from datetime import timedelta
            first = selected_date.replace(day=1)
            if selected_date.month == 12:
                last = selected_date.replace(year=selected_date.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                last = selected_date.replace(month=selected_date.month + 1, day=1) - timedelta(days=1)
            p1 = export_sales_excel(first, last)
            p2 = export_expenses_excel(first, last)
            for path in (p1, p2):
                with open(path, "rb") as f:
                    data = f.read()
                await _dl_picker.save_file(file_name=os.path.basename(path), src_bytes=data)
            show_toast(page, "Reporte mensual exportado correctamente", is_success=True)
        except Exception as exc:
            show_toast(page, f"Error al exportar: {exc}", is_error=True)

    async def _export_pdf(e):
        try:
            import os
            path = export_daily_summary_excel(selected_date)
            with open(path, "rb") as f:
                data = f.read()
            await _dl_picker.save_file(file_name=os.path.basename(path), src_bytes=data)
            show_toast(page, "Reporte diario generado correctamente", is_success=True)
        except Exception as exc:
            show_toast(page, f"Error al generar reporte: {exc}", is_error=True)

    def _get_worker_shift(for_date: date):
        """Devuelve (ShiftType, start_time, end_time) del turno del usuario en for_date, o None."""
        week_start = for_date - timedelta(days=for_date.weekday())
        day_of_week = for_date.weekday()
        session = get_session()
        try:
            sched = session.query(Schedule).filter_by(
                user_id=user.id,
                week_start=week_start,
                day_of_week=day_of_week,
            ).first()
            if sched is None:
                return None
            hour = int(sched.start_time.split(":")[0])
            shift_type = ShiftType.MORNING if hour < 12 else ShiftType.NIGHT
            return shift_type, sched.start_time, sched.end_time
        finally:
            session.close()

    async def _export_shift_pdf(e):
        try:
            import os
            result = _get_worker_shift(selected_date)
            if result is None:
                show_toast(page, "No tienes turno asignado para este día", is_error=True)
                return
            shift_type, start_time, end_time = result
            path = export_shift_summary_excel(
                for_date=selected_date,
                shift_type=shift_type,
                user_name=user.name,
                start_time=start_time,
                end_time=end_time,
            )
            with open(path, "rb") as f:
                data = f.read()
            await _dl_picker.save_file(file_name=os.path.basename(path), src_bytes=data)
            show_toast(page, "Reporte de turno generado correctamente", is_success=True)
        except Exception as exc:
            show_toast(page, f"Error al generar reporte: {exc}", is_error=True)

    # ── Layout ──

    cal = calendar_picker(on_date_selected=_on_date_selected, initial_date=selected_date,
                          cal_width=r_calendar_width(page))
    initial_content = _build_content(selected_date)

    action_buttons = ft.Row([
        ft.ElevatedButton(
            content=ft.Row([ft.Icon(ft.Icons.POINT_OF_SALE, size=16, color="white"),
                            ft.Text("Registrar Venta", size=SMALL_SIZE, color="white")], spacing=4),
            bgcolor=SUCCESS, on_click=_add_sale,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6),
                                 padding=ft.padding.symmetric(horizontal=12, vertical=8)),
        ),
        ft.ElevatedButton(
            content=ft.Row([ft.Icon(ft.Icons.MONEY_OFF, size=16, color="white"),
                            ft.Text("Registrar Gasto", size=SMALL_SIZE, color="white")], spacing=4),
            bgcolor=ERROR, on_click=_add_expense,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6),
                                 padding=ft.padding.symmetric(horizontal=12, vertical=8)),
        ),
        ft.ElevatedButton(
            content=ft.Row([ft.Icon(ft.Icons.SUMMARIZE, size=16, color="white"),
                            ft.Text("Reporte Mensual", size=SMALL_SIZE, color="white")], spacing=4),
            bgcolor="#2E7D32", on_click=_export_excel,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6),
                                 padding=ft.padding.symmetric(horizontal=12, vertical=8)),
        ),
        ft.ElevatedButton(
            content=ft.Row([ft.Icon(ft.Icons.TODAY, size=16, color="white"),
                            ft.Text("Reporte Diario", size=SMALL_SIZE, color="white")], spacing=4),
            bgcolor="#C62828", on_click=_export_pdf,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6),
                                 padding=ft.padding.symmetric(horizontal=12, vertical=8)),
        ),
        *([ft.ElevatedButton(
            content=ft.Row([ft.Icon(ft.Icons.ACCESS_TIME, size=16, color="white"),
                            ft.Text("Reporte de Turno", size=SMALL_SIZE, color="white")], spacing=4),
            bgcolor="#6A1B9A", on_click=_export_shift_pdf,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6),
                                 padding=ft.padding.symmetric(horizontal=12, vertical=8)),
        )] if user.role == UserRole.WORKER else []),
    ], spacing=8, wrap=True)

    mobile = is_mobile(page)
    main_col = ft.Column(
        [
            ft.Row([
                ft.Column([
                    ft.Text("Cuenta", size=r_font_title(page), weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
                    ft.Text("Ventas, gastos y salarios", size=BODY_SIZE, color=TEXT_SECONDARY),
                ], spacing=4, expand=True),
                action_buttons,
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Container(height=8),
            ft.Column(initial_content, ref=content_area, spacing=16, scroll=ft.ScrollMode.AUTO, expand=True),
        ],
        expand=True,
    )

    return ft.Container(
        content=responsive_layout(page, main_col, cal),
        padding=r_padding(page),
        expand=True,
    )
