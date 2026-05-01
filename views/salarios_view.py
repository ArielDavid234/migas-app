import flet as ft
from datetime import date, datetime
from database.db import get_session
from database.models import User, UserRole, ClockRecord, MonthlySalaryPayment
from components.date_field import make_date_field
from utils.responsive import r_padding, r_font_title, r_dialog_width, is_phone
from utils.toast import show_toast
from utils.audit import log_action
from assets.styles import (
    PRIMARY, PRIMARY_DARK, SURFACE, SUCCESS, ERROR, ACCENT,
    TEXT_PRIMARY, TEXT_SECONDARY, FONT_FAMILY, SUBTITLE_SIZE, BODY_SIZE, SMALL_SIZE, DIVIDER_COLOR,
)

MESES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


def salarios_view(page: ft.Page, user: User):
    """Vista de Salarios — solo administradores.
    Muestra horas acumuladas sin pagar por trabajador desde la última certificación.
    """

    content_area = ft.Ref[ft.Column]()

    # ── helpers ──────────────────────────────────────────────────

    def _last_payment_cutoff(worker_id: int, session) -> datetime | None:
        """Fecha/hora del último pago certificado. Acumular horas solo DESPUÉS de ese momento."""
        rec = (
            session.query(MonthlySalaryPayment)
            .filter_by(user_id=worker_id, is_paid=True)
            .order_by(MonthlySalaryPayment.paid_date.desc(), MonthlySalaryPayment.id.desc())
            .first()
        )
        if rec and rec.paid_date:
            # Use end-of-day of the paid_date as cutoff
            return datetime.combine(rec.paid_date, datetime.max.time().replace(microsecond=0))
        return None

    def _calc_accumulated(worker_id: int, since: datetime | None, session) -> float:
        q = session.query(ClockRecord).filter(
            ClockRecord.user_id == worker_id,
            ClockRecord.clock_out.isnot(None),
        )
        if since:
            q = q.filter(ClockRecord.clock_in > since)
        return round(sum(r.hours_worked for r in q.all()), 2)

    def _load_workers() -> list:
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
                cutoff = _last_payment_cutoff(w.id, session)
                hours = _calc_accumulated(w.id, cutoff, session)
                # Payment history (newest first)
                history = (
                    session.query(MonthlySalaryPayment)
                    .filter_by(user_id=w.id, is_paid=True)
                    .order_by(MonthlySalaryPayment.paid_date.desc())
                    .all()
                )
                result.append({
                    "worker_id": w.id,
                    "name": w.name,
                    "rate": w.hourly_rate,
                    "accumulated_hours": hours,
                    "accumulated_earned": round(hours * w.hourly_rate, 2),
                    "last_paid_date": cutoff.date() if cutoff else None,
                    "history": [
                        {
                            "paid_date": h.paid_date,
                            "hours": h.hours_worked,
                            "amount": h.amount,
                            "notes": h.notes or "",
                            "id": h.id,
                        }
                        for h in history
                    ],
                })
            return result
        finally:
            session.close()

    # ── diálogo certificar pago ──────────────────────────────────

    def _open_certify_dialog(wdata: dict):
        ph = is_phone(page)
        w = r_dialog_width(page) - 48 if not ph else None

        amount_field = ft.TextField(
            label="Monto a pagar ($)",
            value=f"{wdata['accumulated_earned']:.2f}",
            expand=ph, width=w,
            border_color=PRIMARY, text_size=BODY_SIZE,
            prefix_icon=ft.Icons.ATTACH_MONEY, autofocus=True,
        )
        paid_date_field = make_date_field(
            "Fecha de pago",
            value=date.today().strftime("%d/%m/%Y"),
            expand=ph, width=w,
            border_color=PRIMARY, text_size=BODY_SIZE,
        )
        notes_field = ft.TextField(
            label="Notas (opcional)",
            expand=ph, width=w,
            border_color=PRIMARY, text_size=BODY_SIZE,
            multiline=True, min_lines=2, max_lines=3,
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
                w_obj = session.query(User).get(wdata["worker_id"])
                cutoff = _last_payment_cutoff(wdata["worker_id"], session)
                hrs = _calc_accumulated(wdata["worker_id"], cutoff, session)
                rec = MonthlySalaryPayment(
                    user_id=wdata["worker_id"],
                    month=pd.replace(day=1),
                    hours_worked=hrs,
                    hourly_rate=w_obj.hourly_rate,
                    amount=amt,
                    is_paid=True,
                    paid_date=pd,
                    notes=notes_field.value.strip(),
                )
                session.add(rec)
                session.commit()
                log_action(
                    user.id, "CREATE", "MonthlySalaryPayment", None,
                    f"{wdata['name']} — {hrs:.1f}h — ${amt:.2f}",
                )
            finally:
                session.close()

            page.pop_dialog()
            show_toast(page, f"Pago de {wdata['name']} certificado ({hrs:.1f}h — ${amt:.2f})", is_success=True)
            _refresh()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(ft.Icons.VERIFIED, color=SUCCESS, size=24),
                ft.Text(f"Certificar Pago — {wdata['name']}", size=SUBTITLE_SIZE,
                        weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
            ], spacing=8),
            content=ft.Container(
                content=ft.Column([
                    ft.Container(
                        content=ft.Column([
                            ft.Text("Horas acumuladas sin pagar", size=SMALL_SIZE, color=TEXT_SECONDARY),
                            ft.Text(
                                f"{wdata['accumulated_hours']:.2f} h  ×  ${wdata['rate']:.2f}/h  =  ${wdata['accumulated_earned']:,.2f}",
                                size=BODY_SIZE, weight=ft.FontWeight.W_600, color=PRIMARY_DARK,
                            ),
                            ft.Text(
                                f"Desde: {wdata['last_paid_date'].strftime('%d/%m/%Y') if wdata['last_paid_date'] else 'Inicio'}",
                                size=SMALL_SIZE, color=TEXT_SECONDARY,
                            ),
                        ], spacing=2),
                        bgcolor=ft.Colors.with_opacity(0.05, PRIMARY),
                        border_radius=8,
                        padding=10,
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
                ft.TextButton(content=ft.Text("Cancelar"), on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton(
                    content=ft.Text("Certificar Pago", color="white"),
                    bgcolor=SUCCESS,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                    on_click=_save,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(dlg)

    # ── tarjeta de trabajador ────────────────────────────────────

    def _worker_card(wdata: dict) -> ft.Container:
        hours = wdata["accumulated_hours"]
        earned = wdata["accumulated_earned"]
        has_hours = hours > 0

        # Historial de pagos (últimos 3)
        history = wdata["history"]
        history_controls = []
        if history:
            history_controls.append(
                ft.Text("Historial de pagos:", size=SMALL_SIZE,
                        color=TEXT_SECONDARY, weight=ft.FontWeight.W_500)
            )
            for h in history[:3]:
                history_controls.append(
                    ft.Row([
                        ft.Icon(ft.Icons.CHECK_CIRCLE, color=SUCCESS, size=14),
                        ft.Text(
                            f"{h['paid_date'].strftime('%d/%m/%Y')}  —  {h['hours']:.1f}h  —  ${h['amount']:,.2f}",
                            size=SMALL_SIZE, color=TEXT_SECONDARY,
                        ),
                        ft.Text(h["notes"], size=SMALL_SIZE, color=TEXT_SECONDARY,
                                italic=True) if h["notes"] else ft.Container(),
                    ], spacing=6)
                )
            if len(history) > 3:
                history_controls.append(
                    ft.Text(f"… y {len(history) - 3} pago(s) más",
                            size=SMALL_SIZE, color=TEXT_SECONDARY, italic=True)
                )
        else:
            history_controls.append(
                ft.Text("Sin pagos previos registrados.", size=SMALL_SIZE,
                        color=TEXT_SECONDARY, italic=True)
            )

        certify_btn = ft.ElevatedButton(
            content=ft.Row([
                ft.Icon(ft.Icons.VERIFIED, size=16, color="white"),
                ft.Text("Certificar Pago", size=SMALL_SIZE, color="white"),
            ], spacing=4),
            bgcolor=SUCCESS if has_hours else TEXT_SECONDARY,
            disabled=not has_hours,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
            on_click=lambda e, w=wdata: _open_certify_dialog(w),
        )

        since_label = (
            f"Desde {wdata['last_paid_date'].strftime('%d/%m/%Y')}"
            if wdata["last_paid_date"] else "Desde el inicio"
        )

        return ft.Container(
            content=ft.Column([
                # Header: nombre + horas + botón
                ft.Row([
                    ft.Icon(ft.Icons.PERSON, color=PRIMARY, size=20),
                    ft.Column([
                        ft.Text(wdata["name"], size=BODY_SIZE,
                                weight=ft.FontWeight.W_600, color=TEXT_PRIMARY),
                        ft.Text(since_label, size=SMALL_SIZE, color=TEXT_SECONDARY),
                    ], spacing=1, expand=True),
                    ft.Column([
                        ft.Text(f"{hours:.2f} h", size=18,
                                weight=ft.FontWeight.BOLD,
                                color=ACCENT if has_hours else TEXT_SECONDARY,
                                text_align=ft.TextAlign.RIGHT),
                        ft.Text(f"${earned:,.2f}", size=SMALL_SIZE,
                                color=PRIMARY_DARK, weight=ft.FontWeight.W_600,
                                text_align=ft.TextAlign.RIGHT),
                    ], spacing=1, horizontal_alignment=ft.CrossAxisAlignment.END),
                    certify_btn,
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                ft.Divider(height=1, color=DIVIDER_COLOR),
                ft.Column(history_controls, spacing=4),
            ], spacing=8),
            padding=ft.padding.symmetric(horizontal=14, vertical=12),
            border_radius=10,
            bgcolor=ft.Colors.with_opacity(0.05, ACCENT if has_hours else SUCCESS),
            border=ft.border.all(1, ft.Colors.with_opacity(0.2, ACCENT if has_hours else SUCCESS)),
        )

    # ── resumen global ───────────────────────────────────────────

    def _build_content() -> list:
        workers = _load_workers()
        total_pending_hours = sum(w["accumulated_hours"] for w in workers)
        total_pending_amount = sum(w["accumulated_earned"] for w in workers)
        workers_with_hours = sum(1 for w in workers if w["accumulated_hours"] > 0)

        controls = []

        # Tarjeta resumen
        controls.append(ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Text("Horas pendientes", size=SMALL_SIZE, color=TEXT_SECONDARY),
                    ft.Text(f"{total_pending_hours:.2f} h", size=20,
                            weight=ft.FontWeight.BOLD, color=ACCENT if total_pending_hours > 0 else TEXT_SECONDARY),
                ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
                ft.VerticalDivider(width=1, color=DIVIDER_COLOR),
                ft.Column([
                    ft.Text("Monto pendiente", size=SMALL_SIZE, color=TEXT_SECONDARY),
                    ft.Text(f"${total_pending_amount:,.2f}", size=20,
                            weight=ft.FontWeight.BOLD, color=ACCENT if total_pending_amount > 0 else TEXT_SECONDARY),
                ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
                ft.VerticalDivider(width=1, color=DIVIDER_COLOR),
                ft.Column([
                    ft.Text("Con horas sin pagar", size=SMALL_SIZE, color=TEXT_SECONDARY),
                    ft.Text(f"{workers_with_hours} / {len(workers)}", size=20,
                            weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
                ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
            ], alignment=ft.MainAxisAlignment.SPACE_EVENLY),
            padding=16, border_radius=12, bgcolor=SURFACE,
            shadow=ft.BoxShadow(spread_radius=0, blur_radius=8,
                                color=ft.Colors.with_opacity(0.1, "black"), offset=ft.Offset(0, 2)),
        ))

        if workers:
            for w in workers:
                controls.append(_worker_card(w))
        else:
            controls.append(ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.PEOPLE_OUTLINE, size=48, color=TEXT_SECONDARY),
                    ft.Text("No hay trabajadores activos registrados.",
                            size=BODY_SIZE, color=TEXT_SECONDARY, italic=True,
                            text_align=ft.TextAlign.CENTER),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                padding=32, alignment=ft.Alignment(0, 0),
            ))

        return controls

    def _refresh():
        content_area.current.controls.clear()
        content_area.current.controls.extend(_build_content())
        content_area.current.update()

    # ── layout ───────────────────────────────────────────────────

    main_col = ft.Column([
        ft.Row([
            ft.Column([
                ft.Text("Salarios", size=r_font_title(page),
                        weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
                ft.Text("Horas acumuladas sin pagar — solo administradores",
                        size=BODY_SIZE, color=TEXT_SECONDARY),
            ], spacing=4, expand=True),
        ]),
        ft.Container(height=4),
        ft.Column(
            _build_content(),
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
