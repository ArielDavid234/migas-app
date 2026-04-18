import flet as ft
from datetime import datetime, date, timedelta
from collections import OrderedDict
from database.db import get_session
from database.models import User, UserRole, ClockRecord, Sale, Expense, Product, Service
from sqlalchemy import func
from assets.styles import (
    PRIMARY, PRIMARY_DARK, PRIMARY_LIGHT, SURFACE, SUCCESS, ERROR, ACCENT,
    TEXT_PRIMARY, TEXT_SECONDARY, FONT_FAMILY, TITLE_SIZE, SUBTITLE_SIZE, BODY_SIZE, SMALL_SIZE, DIVIDER_COLOR,
)
from config import GAS_STATION_NAME, LOW_STOCK_THRESHOLD, EXPIRY_ALERT_DAYS
from components.calendar_picker import calendar_picker
from components.report_form import report_form_dialog
from components.sale_form import sale_form_dialog
from components.expense_form import expense_form_dialog
from utils.responsive import is_mobile, is_phone, responsive_layout, r_padding, r_spacing, r_font_title, r_font_subtitle, r_font_body, r_font_small, r_icon, r_side_panel_width, r_calendar_width
from components.expense_form import expense_form_dialog


def dashboard_view(page: ft.Page, user: User, on_navigate=None):
    """Panel principal con resumen del día, calendario y alertas."""

    selected_date = date.today()

    def _load_data(for_date: date):
        session = get_session()
        try:
            daily_sales = session.query(func.coalesce(func.sum(Sale.amount), 0)).filter(
                Sale.date == for_date
            ).scalar()

            daily_expenses = session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
                Expense.date == for_date
            ).scalar()

            active_workers = session.query(ClockRecord).filter(
                ClockRecord.clock_out.is_(None)
            ).count()

            total_workers = session.query(User).filter_by(is_active=True, role=UserRole.WORKER).count()

            # Productos con stock bajo
            low_stock = session.query(Product).filter(
                Product.stock <= Product.min_stock
            ).all()

            # Productos próximos a vencer
            alert_date = date.today() + timedelta(days=EXPIRY_ALERT_DAYS)
            expiring = session.query(Product).filter(
                Product.expiry_date.isnot(None),
                Product.expiry_date <= alert_date,
                Product.expiry_date >= date.today(),
            ).all()

            # Servicios próximos a vencer (7 días)
            upcoming_services = session.query(Service).filter(
                Service.is_paid == False,
                Service.due_date <= alert_date,
            ).all()

            # Ventas del mes
            first_of_month = for_date.replace(day=1)
            if for_date.month == 12:
                last_of_month = for_date.replace(year=for_date.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                last_of_month = for_date.replace(month=for_date.month + 1, day=1) - timedelta(days=1)

            monthly_sales = session.query(func.coalesce(func.sum(Sale.amount), 0)).filter(
                Sale.date >= first_of_month,
                Sale.date <= last_of_month,
            ).scalar()

            monthly_expenses = session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
                Expense.date >= first_of_month,
                Expense.date <= last_of_month,
            ).scalar()

            # Weekly data for chart (last 7 days)
            weekly_sales = OrderedDict()
            weekly_expenses = OrderedDict()
            for i in range(6, -1, -1):
                d = for_date - timedelta(days=i)
                weekly_sales[d] = 0.0
                weekly_expenses[d] = 0.0

            week_start = for_date - timedelta(days=6)
            rows_s = session.query(Sale.date, func.sum(Sale.amount)).filter(
                Sale.date >= week_start, Sale.date <= for_date
            ).group_by(Sale.date).all()
            for d_row, total in rows_s:
                if d_row in weekly_sales:
                    weekly_sales[d_row] = float(total)

            rows_e = session.query(Expense.date, func.sum(Expense.amount)).filter(
                Expense.date >= week_start, Expense.date <= for_date
            ).group_by(Expense.date).all()
            for d_row, total in rows_e:
                if d_row in weekly_expenses:
                    weekly_expenses[d_row] = float(total)

            return {
                "daily_sales": daily_sales,
                "daily_expenses": daily_expenses,
                "active_workers": active_workers,
                "total_workers": total_workers,
                "low_stock": low_stock,
                "expiring": expiring,
                "upcoming_services": upcoming_services,
                "monthly_sales": monthly_sales,
                "monthly_expenses": monthly_expenses,
                "weekly_sales": weekly_sales,
                "weekly_expenses": weekly_expenses,
            }
        finally:
            session.close()

    data = _load_data(selected_date)

    # --- Stat Cards ---
    def stat_card(title, value, icon, color):
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(icon, color=color, size=r_icon(page, 28)),
                            ft.Text(title, size=r_font_body(page), color=TEXT_SECONDARY),
                        ],
                        spacing=8,
                    ),
                    ft.Text(
                        value,
                        size=r_font_subtitle(page),
                        weight=ft.FontWeight.BOLD,
                        color=TEXT_PRIMARY,
                        font_family=FONT_FAMILY,
                    ),
                ],
                spacing=8,
            ),
            padding=20,
            border_radius=12,
            bgcolor=SURFACE,
            shadow=ft.BoxShadow(
                spread_radius=0, blur_radius=8,
                color=ft.Colors.with_opacity(0.1, "black"),
                offset=ft.Offset(0, 2),
            ),
            col={"xs": 6, "md": 3},
        )

    stats_row = ft.Ref[ft.ResponsiveRow]()
    date_subtitle = ft.Ref[ft.Text]()
    alerts_column = ft.Ref[ft.Column]()
    monthly_column = ft.Ref[ft.Column]()
    chart_container = ft.Ref[ft.Container]()

    def _build_stats(d):
        balance = d["daily_sales"] - d["daily_expenses"]
        return [
            stat_card("Ventas Hoy", f"${d['daily_sales']:,.2f}", ft.Icons.TRENDING_UP, SUCCESS),
            stat_card("Gastos Hoy", f"${d['daily_expenses']:,.2f}", ft.Icons.TRENDING_DOWN, ERROR),
            stat_card("Balance", f"${balance:,.2f}", ft.Icons.ACCOUNT_BALANCE, PRIMARY if balance >= 0 else ERROR),
            stat_card("Activos", f"{d['active_workers']}/{d['total_workers']}", ft.Icons.PEOPLE, ACCENT),
        ]

    def _build_alerts(d):
        items = []

        for p in d["low_stock"][:5]:
            items.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.WARNING_AMBER, color=ACCENT, size=18),
                            ft.Text(f"Stock bajo: {p.name} ({p.stock} uds)", size=SMALL_SIZE, color=TEXT_PRIMARY, expand=True),
                        ],
                        spacing=8,
                    ),
                    padding=ft.padding.symmetric(horizontal=12, vertical=8),
                    border_radius=8,
                    bgcolor=ft.Colors.with_opacity(0.08, ACCENT),
                )
            )

        for p in d["expiring"][:5]:
            days_left = (p.expiry_date - date.today()).days
            items.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.TIMER, color=ERROR, size=18),
                            ft.Text(f"Vence en {days_left}d: {p.name}", size=SMALL_SIZE, color=TEXT_PRIMARY, expand=True),
                        ],
                        spacing=8,
                    ),
                    padding=ft.padding.symmetric(horizontal=12, vertical=8),
                    border_radius=8,
                    bgcolor=ft.Colors.with_opacity(0.08, ERROR),
                )
            )

        for s in d["upcoming_services"]:
            days_left = (s.due_date - date.today()).days
            items.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.RECEIPT_LONG, color=PRIMARY, size=18),
                            ft.Text(
                                f"Pago de {s.name} en {days_left}d ({s.due_date.strftime('%d/%m')})",
                                size=SMALL_SIZE, color=TEXT_PRIMARY, expand=True,
                            ),
                        ],
                        spacing=8,
                    ),
                    padding=ft.padding.symmetric(horizontal=12, vertical=8),
                    border_radius=8,
                    bgcolor=ft.Colors.with_opacity(0.08, PRIMARY),
                )
            )

        if not items:
            items.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.CHECK_CIRCLE, color=SUCCESS, size=18),
                            ft.Text("Todo en orden. Sin alertas.", size=SMALL_SIZE, color=TEXT_SECONDARY),
                        ],
                        spacing=8,
                    ),
                    padding=ft.padding.symmetric(horizontal=12, vertical=8),
                )
            )

        return items

    def _build_monthly(d):
        monthly_balance = d["monthly_sales"] - d["monthly_expenses"]
        color = SUCCESS if monthly_balance >= 0 else ERROR
        sign = "+" if monthly_balance >= 0 else ""
        return [
            ft.Row(
                [ft.Text("Ventas del mes:", size=BODY_SIZE, color=TEXT_SECONDARY, expand=True),
                 ft.Text(f"${d['monthly_sales']:,.2f}", size=BODY_SIZE, weight=ft.FontWeight.BOLD, color=SUCCESS)],
            ),
            ft.Row(
                [ft.Text("Gastos del mes:", size=BODY_SIZE, color=TEXT_SECONDARY, expand=True),
                 ft.Text(f"${d['monthly_expenses']:,.2f}", size=BODY_SIZE, weight=ft.FontWeight.BOLD, color=ERROR)],
            ),
            ft.Divider(height=1, color=DIVIDER_COLOR),
            ft.Row(
                [ft.Text("Balance mensual:", size=BODY_SIZE, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY, expand=True),
                 ft.Text(f"{sign}${monthly_balance:,.2f}", size=SUBTITLE_SIZE, weight=ft.FontWeight.BOLD, color=color)],
            ),
        ]

    def _build_chart(d):
        """Build a weekly bar chart using plain containers (no ft.BarChart)."""
        DAY_ABBR = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
        ws = d["weekly_sales"]
        we = d["weekly_expenses"]
        dates = list(ws.keys())

        all_values = list(ws.values()) + list(we.values())
        max_val = max(all_values) if any(v > 0 for v in all_values) else 100
        chart_h = 160  # max bar height in pixels

        bars = []
        for dt in dates:
            s_h = int((ws[dt] / max_val) * chart_h) if max_val > 0 else 0
            e_h = int((we[dt] / max_val) * chart_h) if max_val > 0 else 0

            sale_bar = ft.Container(
                width=16, height=max(s_h, 2), bgcolor=SUCCESS,
                border_radius=ft.border_radius.only(top_left=4, top_right=4),
                tooltip=f"Ventas: ${ws[dt]:,.2f}",
            )
            exp_bar = ft.Container(
                width=16, height=max(e_h, 2), bgcolor=ERROR,
                border_radius=ft.border_radius.only(top_left=4, top_right=4),
                tooltip=f"Gastos: ${we[dt]:,.2f}",
            )

            day_col = ft.Column(
                [
                    ft.Row([sale_bar, exp_bar], spacing=3, alignment=ft.MainAxisAlignment.CENTER),
                    ft.Text(DAY_ABBR[dt.weekday()], size=11, color=TEXT_SECONDARY, text_align=ft.TextAlign.CENTER),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.END,
                spacing=4,
                height=chart_h + 24,
            )
            bars.append(day_col)

        chart = ft.Container(
            content=ft.Row(
                bars,
                alignment=ft.MainAxisAlignment.SPACE_EVENLY,
                vertical_alignment=ft.CrossAxisAlignment.END,
            ),
            border=ft.Border(bottom=ft.BorderSide(1, DIVIDER_COLOR)),
            padding=ft.padding.only(top=8, bottom=0, left=4, right=4),
        )

        legend = ft.Row(
            [
                ft.Row([ft.Container(width=12, height=12, bgcolor=SUCCESS, border_radius=3), ft.Text("Ventas", size=SMALL_SIZE, color=TEXT_SECONDARY)], spacing=4),
                ft.Row([ft.Container(width=12, height=12, bgcolor=ERROR, border_radius=3), ft.Text("Gastos", size=SMALL_SIZE, color=TEXT_SECONDARY)], spacing=4),
            ],
            spacing=16,
            alignment=ft.MainAxisAlignment.CENTER,
        )

        return ft.Column([chart, legend], spacing=8)

    def _on_date_selected(d: date):
        nonlocal selected_date, data
        selected_date = d
        data = _load_data(d)
        # Update stats
        stats_row.current.controls.clear()
        stats_row.current.controls.extend(_build_stats(data))
        stats_row.current.update()
        # Update date label
        date_subtitle.current.value = f"Principal — {d.strftime('%d/%m/%Y')}"
        date_subtitle.current.update()
        # Update alerts
        alerts_column.current.controls.clear()
        alerts_column.current.controls.extend(_build_alerts(data))
        alerts_column.current.update()
        # Update monthly
        monthly_column.current.controls.clear()
        monthly_column.current.controls.extend(_build_monthly(data))
        monthly_column.current.update()
        # Update chart
        chart_container.current.content = _build_chart(data)
        chart_container.current.update()

    def _refresh_dashboard():
        nonlocal data
        data = _load_data(selected_date)
        stats_row.current.controls.clear()
        stats_row.current.controls.extend(_build_stats(data))
        stats_row.current.update()
        alerts_column.current.controls.clear()
        alerts_column.current.controls.extend(_build_alerts(data))
        alerts_column.current.update()
        monthly_column.current.controls.clear()
        monthly_column.current.controls.extend(_build_monthly(data))
        monthly_column.current.update()
        chart_container.current.content = _build_chart(data)
        chart_container.current.update()

    def _open_new_report(e):
        report_form_dialog(page, user.id, on_saved=_refresh_dashboard)

    def _open_new_sale(e):
        sale_form_dialog(page, user.id, on_saved=_refresh_dashboard)

    def _open_new_expense(e):
        expense_form_dialog(page, on_saved=_refresh_dashboard)

    def _go_inventario(e):
        if on_navigate:
            on_navigate("inventario")

    # --- Layout ---
    header = ft.Container(
        content=ft.Row(
            [
                ft.Column(
                    [
                        ft.Text(
                            GAS_STATION_NAME,
                            size=r_font_title(page),
                            weight=ft.FontWeight.BOLD,
                            color=PRIMARY_DARK,
                            font_family=FONT_FAMILY,
                        ),
                        ft.Text(
                            f"Principal — {selected_date.strftime('%d/%m/%Y')}",
                            ref=date_subtitle,
                            size=BODY_SIZE,
                            color=TEXT_SECONDARY,
                        ),
                    ],
                    spacing=4,
                ),
                ft.Container(
                    content=ft.Text(
                        f"Bienvenido, {user.name}",
                        size=BODY_SIZE,
                        color=TEXT_SECONDARY,
                        italic=True,
                        text_align=ft.TextAlign.RIGHT,
                        overflow=ft.TextOverflow.VISIBLE,
                    ),
                    expand=True,
                    alignment=ft.Alignment(1, 0),
                    padding=ft.padding.only(left=12, right=4),
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
        padding=ft.padding.only(bottom=16),
    )

    def _card_wrapper(title, icon, content_controls):
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(icon, color=PRIMARY_DARK, size=20),
                            ft.Text(title, size=BODY_SIZE, weight=ft.FontWeight.W_600, color=TEXT_PRIMARY),
                        ],
                        spacing=8,
                    ),
                    ft.Divider(height=1, color=DIVIDER_COLOR),
                    *content_controls,
                ],
                spacing=8,
            ),
            padding=16,
            border_radius=12,
            bgcolor=SURFACE,
            shadow=ft.BoxShadow(
                spread_radius=0, blur_radius=8,
                color=ft.Colors.with_opacity(0.1, "black"),
                offset=ft.Offset(0, 2),
            ),
        )

    # Right column: calendar + alerts + monthly
    cal = calendar_picker(on_date_selected=_on_date_selected, initial_date=selected_date,
                          cal_width=r_calendar_width(page))

    alerts_content = _build_alerts(data)
    monthly_content = _build_monthly(data)

    right_panel = ft.Column(
        [
            cal,
            _card_wrapper(
                "Alertas",
                ft.Icons.NOTIFICATIONS_ACTIVE,
                [ft.Column(alerts_content, ref=alerts_column, spacing=4)],
            ),
            _card_wrapper(
                "Resumen Mensual",
                ft.Icons.CALENDAR_MONTH,
                [ft.Column(monthly_content, ref=monthly_column, spacing=6)],
            ),
        ],
        spacing=16,
        width=r_side_panel_width(page),
        scroll=ft.ScrollMode.AUTO,
    )

    # Main content
    pad = r_padding(page)
    sp = r_spacing(page)
    main_content = ft.Column(
        [
            header,
            ft.ResponsiveRow(
                _build_stats(data),
                ref=stats_row,
                spacing=sp,
            ),
            ft.Container(height=8),
            # Weekly chart
            _card_wrapper(
                "Ventas vs Gastos (Últimos 7 días)",
                ft.Icons.BAR_CHART,
                [ft.Container(content=_build_chart(data), ref=chart_container)],
            ),
            ft.Container(height=8),
            # Quick info section
            _card_wrapper(
                "Accesos Rápidos",
                ft.Icons.FLASH_ON,
                [
                    ft.Row(
                        [
                            _quick_action_btn("Nuevo Reporte", ft.Icons.NOTE_ADD, PRIMARY, _open_new_report),
                            _quick_action_btn("Registrar Venta", ft.Icons.POINT_OF_SALE, SUCCESS, _open_new_sale),
                            _quick_action_btn("Registrar Gasto", ft.Icons.MONEY_OFF, ERROR, _open_new_expense),
                            _quick_action_btn("Ver Inventario", ft.Icons.INVENTORY_2, ACCENT, _go_inventario),
                        ],
                        spacing=sp,
                        wrap=True,
                    ),
                ],
            ),
        ],
        spacing=12,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )

    return ft.Container(
        content=responsive_layout(page, main_content, right_panel),
        padding=pad,
        expand=True,
    )


def _quick_action_btn(label, icon, color, on_click):
    return ft.ElevatedButton(
        content=ft.Row(
            [
                ft.Icon(icon, color="white", size=18),
                ft.Text(label, color="white", size=12, weight=ft.FontWeight.W_500),
            ],
            spacing=6,
            tight=True,
        ),
        bgcolor=color,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.padding.symmetric(horizontal=16, vertical=10),
        ),
        on_click=on_click,
    )
