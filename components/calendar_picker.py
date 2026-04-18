import flet as ft
from datetime import date, timedelta
import calendar
from assets.styles import (
    PRIMARY, PRIMARY_LIGHT, PRIMARY_DARK, SURFACE, TEXT_PRIMARY,
    TEXT_SECONDARY, FONT_FAMILY, BODY_SIZE, SMALL_SIZE, DIVIDER_COLOR,
)

DAYS_ES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
MONTHS_ES = [
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


def calendar_picker(on_date_selected, initial_date: date | None = None, cal_width: int | None = None):
    """
    Componente de calendario reutilizable.
    - on_date_selected(selected_date: date): callback cuando se selecciona un día.
    - initial_date: fecha inicial seleccionada (default: hoy).
    - cal_width: explicit width (None = expand to fill parent).
    Retorna un ft.Container que se puede insertar en cualquier vista.
    """
    w = cal_width or 300
    cell = max(28, w // 9)  # scale day cells to fit
    selected = initial_date or date.today()
    current_year = selected.year
    current_month = selected.month

    # Refs para actualizar dinámicamente
    month_label = ft.Ref[ft.Text]()
    days_grid = ft.Ref[ft.Column]()
    selected_label = ft.Ref[ft.Text]()

    def _build_days_grid(year, month, sel_date):
        """Construye la grilla de días del mes."""
        cal = calendar.Calendar(firstweekday=0)  # Lunes primero
        month_days = cal.monthdayscalendar(year, month)

        rows = []
        # Header con días de la semana
        header = ft.Row(
            [
                ft.Container(
                    content=ft.Text(
                        d, size=SMALL_SIZE, weight=ft.FontWeight.BOLD,
                        color=TEXT_SECONDARY, text_align=ft.TextAlign.CENTER,
                    ),
                    width=cell, height=cell - 8,
                    alignment=ft.Alignment(0, 0),
                )
                for d in DAYS_ES
            ],
            spacing=2,
            alignment=ft.MainAxisAlignment.CENTER,
        )
        rows.append(header)

        for week in month_days:
            week_row = []
            for day_num in week:
                if day_num == 0:
                    week_row.append(ft.Container(width=cell, height=cell))
                else:
                    d = date(year, month, day_num)
                    is_today = d == date.today()
                    is_selected = d == sel_date

                    if is_selected:
                        bg = PRIMARY
                        text_color = "white"
                    elif is_today:
                        bg = PRIMARY_LIGHT
                        text_color = "white"
                    else:
                        bg = "transparent"
                        text_color = TEXT_PRIMARY

                    week_row.append(
                        ft.Container(
                            content=ft.Text(
                                str(day_num), size=BODY_SIZE,
                                color=text_color, text_align=ft.TextAlign.CENTER,
                                weight=ft.FontWeight.BOLD if is_selected or is_today else ft.FontWeight.NORMAL,
                            ),
                            width=cell, height=cell,
                            border_radius=cell // 2,
                            bgcolor=bg,
                            alignment=ft.Alignment(0, 0),
                            on_click=lambda e, dd=d: _on_day_click(dd),
                            on_hover=lambda e, sel=is_selected: _on_day_hover(e, sel),
                            animate=ft.Animation(150, ft.AnimationCurve.EASE_IN_OUT),
                        )
                    )

            rows.append(
                ft.Row(week_row, spacing=2, alignment=ft.MainAxisAlignment.CENTER)
            )

        return rows

    def _on_day_hover(e, is_selected):
        if not is_selected:
            e.control.bgcolor = ft.Colors.with_opacity(0.1, PRIMARY) if e.data == "true" else "transparent"
            e.control.update()

    def _on_day_click(d: date):
        nonlocal selected
        selected = d
        _refresh()
        on_date_selected(d)

    def _change_month(delta):
        nonlocal current_month, current_year
        current_month += delta
        if current_month > 12:
            current_month = 1
            current_year += 1
        elif current_month < 1:
            current_month = 12
            current_year -= 1
        _refresh()

    def _go_today(e):
        nonlocal selected, current_month, current_year
        today = date.today()
        selected = today
        current_month = today.month
        current_year = today.year
        _refresh()
        on_date_selected(today)

    def _refresh():
        month_label.current.value = f"{MONTHS_ES[current_month]} {current_year}"
        month_label.current.update()

        selected_label.current.value = selected.strftime("%d/%m/%Y")
        selected_label.current.update()

        grid = days_grid.current
        grid.controls.clear()
        grid.controls.extend(_build_days_grid(current_year, current_month, selected))
        grid.update()

    initial_grid = _build_days_grid(current_year, current_month, selected)

    return ft.Container(
        content=ft.Column(
            [
                # Navigation: < Month Year >
                ft.Row(
                    [
                        ft.IconButton(
                            icon=ft.Icons.CHEVRON_LEFT,
                            icon_color=PRIMARY_DARK,
                            icon_size=20,
                            on_click=lambda e: _change_month(-1),
                            tooltip="Mes anterior",
                        ),
                        ft.Text(
                            f"{MONTHS_ES[current_month]} {current_year}",
                            ref=month_label,
                            size=BODY_SIZE,
                            weight=ft.FontWeight.BOLD,
                            color=PRIMARY_DARK,
                            text_align=ft.TextAlign.CENTER,
                            expand=True,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.CHEVRON_RIGHT,
                            icon_color=PRIMARY_DARK,
                            icon_size=20,
                            on_click=lambda e: _change_month(1),
                            tooltip="Mes siguiente",
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                # Days grid
                ft.Column(
                    initial_grid,
                    ref=days_grid,
                    spacing=2,
                ),
                ft.Divider(height=1, color=DIVIDER_COLOR),
                # Footer: today button + selected date
                ft.Row(
                    [
                        ft.TextButton(
                            content=ft.Text("Hoy"),
                            on_click=_go_today,
                            style=ft.ButtonStyle(color=PRIMARY),
                        ),
                        ft.Text(
                            selected.strftime("%d/%m/%Y"),
                            ref=selected_label,
                            size=SMALL_SIZE,
                            color=TEXT_SECONDARY,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            ],
            spacing=4,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=12,
        border_radius=12,
        bgcolor=SURFACE,
        shadow=ft.BoxShadow(
            spread_radius=0, blur_radius=8,
            color=ft.Colors.with_opacity(0.1, "black"),
            offset=ft.Offset(0, 2),
        ),
        width=cal_width,
    )
