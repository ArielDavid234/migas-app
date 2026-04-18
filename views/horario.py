import flet as ft
from datetime import date, timedelta
from database.db import get_session
from database.models import Schedule, User, UserRole, ScheduleNotification
from components.calendar_picker import calendar_picker
from utils.responsive import is_mobile, responsive_layout, r_padding, r_font_title, r_calendar_width, r_dialog_width, r_field_width, is_phone
from components.confirm_dialog import confirm_delete_dialog
from utils.export import export_schedule_excel
from utils.toast import show_toast
from assets.styles import (
    PRIMARY, PRIMARY_DARK, PRIMARY_LIGHT, SURFACE, SUCCESS, ERROR, ACCENT,
    TEXT_PRIMARY, TEXT_SECONDARY, FONT_FAMILY, TITLE_SIZE, SUBTITLE_SIZE, BODY_SIZE, SMALL_SIZE, DIVIDER_COLOR,
)

DAYS_FULL = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def horario_view(page: ft.Page, user):
    """Módulo de Horario: horarios semanales con asignación de turnos."""

    selected_date = date.today()
    schedule_grid = ft.Ref[ft.Column]()

    def _get_week_range(d: date):
        weekday = d.weekday()
        week_start = d - timedelta(days=weekday)
        week_end = week_start + timedelta(days=6)
        return week_start, week_end

    def _load_schedules(week_start: date):
        session = get_session()
        try:
            workers = session.query(User).filter_by(is_active=True, role=UserRole.WORKER).order_by(User.name).all()
            schedules = session.query(Schedule).filter(Schedule.week_start == week_start).all()
            worker_list = [{"id": w.id, "name": w.name} for w in workers]
            sched_map = {}
            for s in schedules:
                if s.user_id not in sched_map:
                    sched_map[s.user_id] = {}
                sched_map[s.user_id][s.day_of_week] = {
                    "id": s.id, "start_time": s.start_time, "end_time": s.end_time,
                }
            return worker_list, sched_map
        finally:
            session.close()

    def _refresh():
        week_start, _ = _get_week_range(selected_date)
        schedule_grid.current.controls.clear()
        schedule_grid.current.controls.extend(_build_schedule_table(week_start))
        schedule_grid.current.update()

    # ── schedule assignment dialog ──

    def _schedule_dialog(worker_id: int, worker_name: str, week_start: date, day_idx: int, existing=None):
        ph = is_phone(page)
        start_field = ft.TextField(
            label="Hora inicio (HH:MM)", width=r_field_width(page, 150), expand=ph, text_size=BODY_SIZE, border_color=PRIMARY,
            value=existing["start_time"] if existing else "06:00", autofocus=True,
        )
        end_field = ft.TextField(
            label="Hora fin (HH:MM)", width=r_field_width(page, 150), expand=ph, text_size=BODY_SIZE, border_color=PRIMARY,
            value=existing["end_time"] if existing else "14:00",
        )
        status_text = ft.Text("", size=BODY_SIZE)

        day_name = DAYS_FULL[day_idx]
        day_date = week_start + timedelta(days=day_idx)

        def _validate_time(val):
            try:
                parts = val.split(":")
                h, m = int(parts[0]), int(parts[1])
                return 0 <= h <= 23 and 0 <= m <= 59
            except (ValueError, IndexError):
                return False

        def _save(e):
            start = start_field.value.strip()
            end = end_field.value.strip()
            if not _validate_time(start) or not _validate_time(end):
                status_text.value = "Formato inválido. Usa HH:MM (ej: 06:00)"
                status_text.color = ERROR
                page.update()
                return

            session = get_session()
            try:
                if existing:
                    sched = session.query(Schedule).get(existing["id"])
                    sched.start_time = start
                    sched.end_time = end
                else:
                    sched = Schedule(
                        user_id=worker_id,
                        week_start=week_start,
                        day_of_week=day_idx,
                        start_time=start,
                        end_time=end,
                    )
                    session.add(sched)
                session.commit()
                # Notify the worker that their schedule has been updated
                existing_notif = session.query(ScheduleNotification).filter_by(
                    user_id=worker_id, week_start=week_start
                ).first()
                if existing_notif:
                    existing_notif.is_read = False
                else:
                    session.add(ScheduleNotification(
                        user_id=worker_id, week_start=week_start, is_read=False
                    ))
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

        def _remove(e):
            if existing:
                def _do():
                    session = get_session()
                    try:
                        s = session.query(Schedule).get(existing["id"])
                        if s:
                            session.delete(s)
                            session.commit()
                    finally:
                        session.close()
                    page.pop_dialog()
                    _refresh()
                confirm_delete_dialog(page, "Quitar Turno", f"¿Quitar el turno de {worker_name} el {day_name}?", _do)

        title = f"{'Editar' if existing else 'Asignar'} Turno"
        actions = [
            ft.TextButton(content=ft.Text("Cancelar"), on_click=lambda e: page.pop_dialog()),
        ]
        if existing:
            actions.insert(0, ft.TextButton(content=ft.Text("Quitar turno"), on_click=_remove,
                                            style=ft.ButtonStyle(color=ERROR)))
        actions.append(ft.ElevatedButton(
            content=ft.Text("Guardar", color="white"), bgcolor=SUCCESS,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
            on_click=_save,
        ))

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(title, size=SUBTITLE_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
            content=ft.Container(
                content=ft.Column([
                    ft.Text(f"{worker_name} — {day_name} {day_date.strftime('%d/%m')}", size=BODY_SIZE,
                            weight=ft.FontWeight.W_500, color=TEXT_PRIMARY),
                    ft.Divider(height=1, color=DIVIDER_COLOR),
                    ft.Row([start_field, end_field], spacing=12),
                    status_text,
                ], spacing=12),
                width=r_dialog_width(page, 360), height=None if ph else 150,
            ),
            actions=actions,
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(dlg)

    # ── build table ──

    def _build_schedule_table(week_start: date):
        workers, sched_map = _load_schedules(week_start)
        week_end = week_start + timedelta(days=6)

        header_cells = [ft.DataColumn(ft.Text("Trabajador", weight=ft.FontWeight.BOLD, size=SMALL_SIZE, color=PRIMARY_DARK))]
        for i, day in enumerate(DAYS_FULL):
            day_date = week_start + timedelta(days=i)
            header_cells.append(ft.DataColumn(
                ft.Text(f"{day}\n{day_date.strftime('%d/%m')}", weight=ft.FontWeight.BOLD,
                        size=SMALL_SIZE, color=PRIMARY_DARK, text_align=ft.TextAlign.CENTER),
            ))

        rows = []
        is_admin = user.role == UserRole.ADMIN
        for w in workers:
            cells = [ft.DataCell(ft.Text(w["name"], size=BODY_SIZE, weight=ft.FontWeight.W_500, color=TEXT_PRIMARY))]
            user_sched = sched_map.get(w["id"], {})
            for day_idx in range(7):
                s = user_sched.get(day_idx)
                if s:
                    cell_content = ft.Container(
                        content=ft.Text(f"{s['start_time']}\n{s['end_time']}", size=SMALL_SIZE,
                                        color="white", text_align=ft.TextAlign.CENTER),
                        bgcolor=PRIMARY, border_radius=6,
                        padding=ft.padding.symmetric(horizontal=8, vertical=4),
                        on_click=(lambda e, wid=w["id"], wname=w["name"], di=day_idx, ex=s: _schedule_dialog(wid, wname, week_start, di, ex)) if is_admin else None,
                        tooltip="Click para editar" if is_admin else None,
                    )
                else:
                    cell_content = ft.Container(
                        content=ft.Text("Libre", size=SMALL_SIZE, color=TEXT_SECONDARY, italic=True,
                                        text_align=ft.TextAlign.CENTER),
                        on_click=(lambda e, wid=w["id"], wname=w["name"], di=day_idx: _schedule_dialog(wid, wname, week_start, di)) if is_admin else None,
                        border_radius=6,
                        padding=ft.padding.symmetric(horizontal=8, vertical=4),
                        tooltip="Click para asignar turno" if is_admin else None,
                    )
                cells.append(ft.DataCell(cell_content))
            rows.append(ft.DataRow(cells=cells))

        if not workers:
            return [ft.Container(
                content=ft.Text("No hay trabajadores registrados", size=BODY_SIZE, color=TEXT_SECONDARY, italic=True),
                padding=20, alignment=ft.Alignment(0, 0),
            )]

        table = ft.DataTable(
            columns=header_cells,
            rows=rows,
            border=ft.border.all(1, DIVIDER_COLOR),
            border_radius=8,
            heading_row_color=ft.Colors.with_opacity(0.05, PRIMARY),
            data_row_max_height=60,
            column_spacing=12,
            horizontal_lines=ft.BorderSide(1, DIVIDER_COLOR),
        )

        return [
            ft.Text(
                f"Semana: {week_start.strftime('%d/%m/%Y')} — {week_end.strftime('%d/%m/%Y')}",
                size=BODY_SIZE, weight=ft.FontWeight.W_600, color=PRIMARY_DARK,
            ),
            ft.Text("Click en una celda para asignar o editar turno", size=SMALL_SIZE, color=TEXT_SECONDARY, italic=True),
            ft.Container(
                content=ft.Row([table], scroll=ft.ScrollMode.AUTO),
                border_radius=12, bgcolor=SURFACE, padding=12,
                shadow=ft.BoxShadow(spread_radius=0, blur_radius=8,
                                    color=ft.Colors.with_opacity(0.1, "black"), offset=ft.Offset(0, 2)),
            ),
        ]

    def _on_date_selected(d: date):
        nonlocal selected_date
        selected_date = d
        week_start, _ = _get_week_range(d)
        schedule_grid.current.controls.clear()
        schedule_grid.current.controls.extend(_build_schedule_table(week_start))
        schedule_grid.current.update()

    week_start, _ = _get_week_range(selected_date)
    initial_table = _build_schedule_table(week_start)
    cal = calendar_picker(on_date_selected=_on_date_selected, initial_date=selected_date,
                          cal_width=r_calendar_width(page))

    _dl_picker = ft.FilePicker()
    page.services.append(_dl_picker)

    async def _download_pdf(e):
        try:
            import os
            ws, _ = _get_week_range(selected_date)
            fid = None if user.role == UserRole.ADMIN else user.id
            path = export_schedule_excel(ws, filter_user_id=fid)
            with open(path, "rb") as f:
                data = f.read()
            await _dl_picker.save_file(file_name=os.path.basename(path), src_bytes=data)
            show_toast(page, "PDF del horario generado correctamente", is_success=True)
        except Exception as ex:
            show_toast(page, f"Error al generar PDF: {ex}", is_error=True)

    # ── Schedule notification banner (workers only) ──
    notif_banner = ft.Ref[ft.Container]()

    def _dismiss_banner(e=None):
        if notif_banner.current:
            notif_banner.current.visible = False
            notif_banner.current.update()

    def _get_unread_notifications() -> list:
        if user.role == UserRole.ADMIN:
            return []
        session = get_session()
        try:
            return session.query(ScheduleNotification).filter_by(
                user_id=user.id, is_read=False
            ).all()
        finally:
            session.close()

    def _mark_notifications_read():
        if user.role == UserRole.ADMIN:
            return
        session = get_session()
        try:
            session.query(ScheduleNotification).filter_by(
                user_id=user.id, is_read=False
            ).update({"is_read": True})
            session.commit()
        finally:
            session.close()

    unread = _get_unread_notifications()
    has_notif = len(unread) > 0
    if has_notif:
        # Mark as read immediately on open
        _mark_notifications_read()
        weeks_str = ", ".join(
            (n.week_start + timedelta(days=6)).strftime("sem. al %d/%m/%Y")
            for n in unread
        )
        banner_text = f"Tienes {'un' if len(unread) == 1 else len(unread)} horario{'s' if len(unread) > 1 else ''} nuevo{'s' if len(unread) > 1 else ''}: {weeks_str}"
    else:
        banner_text = ""

    notif_banner_control = ft.Container(
        ref=notif_banner,
        visible=has_notif,
        content=ft.Row([
            ft.Icon(ft.Icons.NOTIFICATIONS_ACTIVE, color="white", size=18),
            ft.Text(banner_text, color="white", size=BODY_SIZE, expand=True),
            ft.IconButton(ft.Icons.CLOSE, icon_color="white", icon_size=16, on_click=_dismiss_banner),
        ], spacing=8),
        padding=ft.padding.symmetric(horizontal=16, vertical=10),
        border_radius=8,
        bgcolor=PRIMARY_DARK,
    )

    mobile = is_mobile(page)
    main_col = ft.Column([
        ft.Row([
            ft.Column([
                ft.Text("Horario", size=r_font_title(page), weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
                ft.Text("Horarios semanales de los trabajadores", size=BODY_SIZE, color=TEXT_SECONDARY),
            ], expand=True),
            ft.ElevatedButton(
                "Descargar Horario",
                icon=ft.Icons.FILE_DOWNLOAD,
                on_click=_download_pdf,
                style=ft.ButtonStyle(bgcolor="#C62828", color=ft.Colors.WHITE),
            ),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Container(height=8),
        notif_banner_control,
        ft.Text(
            "Click en una celda para asignar o editar turno" if user.role == UserRole.ADMIN else "Solo los administradores pueden modificar horarios",
            size=SMALL_SIZE, color=TEXT_SECONDARY, italic=True,
        ),
        ft.Column(initial_table, ref=schedule_grid, spacing=12, scroll=ft.ScrollMode.AUTO, expand=True),
    ], expand=True)

    return ft.Container(
        content=responsive_layout(page, main_col, cal),
        padding=r_padding(page), expand=True,
    )
