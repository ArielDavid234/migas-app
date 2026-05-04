import flet as ft
from datetime import date
from sqlalchemy.orm import joinedload
from database.db import get_session
from database.models import User, Report, ShiftType, UserRole
from components.calendar_picker import calendar_picker
from components.report_form import report_form_dialog
from components.confirm_dialog import confirm_delete_dialog
from utils.responsive import is_mobile, responsive_layout, r_padding, r_font_title, r_calendar_width, scrollable_row
from utils.export import export_report_excel_bytes, apply_scan_report
from utils.toast import show_toast
from utils.audit import log_action
from assets.styles import (
    PRIMARY, PRIMARY_DARK, PRIMARY_LIGHT, SURFACE, SUCCESS, ERROR, ACCENT,
    TEXT_PRIMARY, TEXT_SECONDARY, FONT_FAMILY, TITLE_SIZE, SUBTITLE_SIZE, BODY_SIZE, SMALL_SIZE, DIVIDER_COLOR,
)


def reportes_view(page: ft.Page, user):
    """Módulo de Reportes: mañana, noche y día completo."""

    selected_date = date.today()
    selected_user_id = None  # None = todos
    content_area = ft.Ref[ft.Column]()
    shift_selector = ft.Ref[ft.SegmentedButton]()
    user_filter_dd = ft.Ref[ft.Dropdown]()

    def _load_workers():
        session = get_session()
        try:
            return session.query(User).order_by(User.name).all()
        finally:
            session.close()

    def _load_reports(d: date, shift: ShiftType | None = None, uid: int | None = None):
        session = get_session()
        try:
            q = (
                session.query(Report)
                .options(
                    joinedload(Report.user),
                    joinedload(Report.cigarette_counts),
                    joinedload(Report.lottery_sales),
                    joinedload(Report.checks),
                    joinedload(Report.tips),
                    joinedload(Report.special_items),
                )
                .filter(Report.date == d)
            )
            if shift:
                q = q.filter(Report.shift == shift)
            if uid:
                q = q.filter(Report.user_id == uid)
            reports = q.all()

            result = []
            for r in reports:
                result.append({
                    "report": r,
                    "user_name": r.user.name if r.user else "—",
                    "cigarettes": r.cigarette_counts,
                    "lottery": r.lottery_sales,
                    "checks": r.checks,
                    "tips": r.tips,
                    "specials": r.special_items,
                })
            return result
        finally:
            session.close()

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

    def _build_cigarette_table(cigs):
        if not cigs:
            return ft.Text("Sin datos de cigarros", size=SMALL_SIZE, color=TEXT_SECONDARY, italic=True)
        rows = []
        for c in cigs:
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(c.brand, size=SMALL_SIZE)),
                ft.DataCell(ft.Text(str(c.boxes_start), size=SMALL_SIZE, text_align=ft.TextAlign.CENTER)),
                ft.DataCell(ft.Text(str(c.sold), size=SMALL_SIZE, text_align=ft.TextAlign.CENTER, color=SUCCESS)),
                ft.DataCell(ft.Text(str(c.boxes_end), size=SMALL_SIZE, text_align=ft.TextAlign.CENTER)),
            ]))
        return scrollable_row([ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Marca", size=SMALL_SIZE, weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Inicio", size=SMALL_SIZE, weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Vendidos", size=SMALL_SIZE, weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Resto", size=SMALL_SIZE, weight=ft.FontWeight.BOLD)),
            ],
            rows=rows, border=ft.border.all(1, DIVIDER_COLOR), border_radius=6,
            heading_row_color=ft.Colors.with_opacity(0.05, PRIMARY),
            column_spacing=20,
        )])

    def _build_lottery_table(lottery):
        if not lottery:
            return ft.Text("Sin datos de lotería", size=SMALL_SIZE, color=TEXT_SECONDARY, italic=True)
        rows = []
        total_scratch = 0
        total_lotto = 0
        for l in lottery:
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(l.scratch_name, size=SMALL_SIZE)),
                ft.DataCell(ft.Text(f"${l.amount:,.2f}", size=SMALL_SIZE, color=SUCCESS)),
                ft.DataCell(ft.Text(f"${l.lotto_amount:,.2f}", size=SMALL_SIZE, color=ACCENT)),
            ]))
            total_scratch += l.amount
            total_lotto += l.lotto_amount

        rows.append(ft.DataRow(cells=[
            ft.DataCell(ft.Text("TOTAL", size=SMALL_SIZE, weight=ft.FontWeight.BOLD)),
            ft.DataCell(ft.Text(f"${total_scratch:,.2f}", size=SMALL_SIZE, weight=ft.FontWeight.BOLD, color=SUCCESS)),
            ft.DataCell(ft.Text(f"${total_lotto:,.2f}", size=SMALL_SIZE, weight=ft.FontWeight.BOLD, color=ACCENT)),
        ]))

        total_all = total_scratch + total_lotto
        return ft.Column([
            scrollable_row([ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Text("Scratch", size=SMALL_SIZE, weight=ft.FontWeight.BOLD)),
                    ft.DataColumn(ft.Text("Ventas", size=SMALL_SIZE, weight=ft.FontWeight.BOLD)),
                    ft.DataColumn(ft.Text("Lotto", size=SMALL_SIZE, weight=ft.FontWeight.BOLD)),
                ],
                rows=rows, border=ft.border.all(1, DIVIDER_COLOR), border_radius=6,
                heading_row_color=ft.Colors.with_opacity(0.05, PRIMARY),
                column_spacing=20,
            )]),
            ft.Container(
                content=ft.Text(f"Total Ventas Lotería: ${total_all:,.2f}", size=BODY_SIZE,
                                weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
                padding=ft.padding.symmetric(horizontal=12, vertical=8),
                bgcolor=ft.Colors.with_opacity(0.08, PRIMARY), border_radius=6,
            ),
        ], spacing=8)

    def _build_specials_table(specials):
        if not specials:
            return ft.Text("Sin datos de ítems especiales", size=SMALL_SIZE, color=TEXT_SECONDARY, italic=True)
        rows = []
        for s in specials:
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(s.item_name, size=SMALL_SIZE)),
                ft.DataCell(ft.Text(str(s.sold), size=SMALL_SIZE, color=SUCCESS, text_align=ft.TextAlign.CENTER)),
                ft.DataCell(ft.Text(str(s.remaining), size=SMALL_SIZE, text_align=ft.TextAlign.CENTER)),
            ]))
        return scrollable_row([ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Producto", size=SMALL_SIZE, weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Vendidos", size=SMALL_SIZE, weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Quedan", size=SMALL_SIZE, weight=ft.FontWeight.BOLD)),
            ],
            rows=rows, border=ft.border.all(1, DIVIDER_COLOR), border_radius=6,
            heading_row_color=ft.Colors.with_opacity(0.05, PRIMARY),
            column_spacing=20,
        )])

    def _delete_report(report_id: int, label: str):
        def _do():
            session = get_session()
            try:
                r = session.query(Report).get(report_id)
                if r:
                    session.delete(r)
                    session.commit()
            finally:
                session.close()
            _refresh_reports()
            show_toast(page, f"Reporte eliminado", is_success=True)
        confirm_delete_dialog(page, "Eliminar Reporte",
                              f"¿Eliminar el reporte de {label}? Esta acción no se puede deshacer.", _do)

    def _build_report_view(report_data):
        rd = report_data
        shift_name = "Mañana" if rd["report"].shift == ShiftType.MORNING else "Noche"
        report_id = rd["report"].id

        checks_total = sum(c.amount for c in rd["checks"])
        tips_total = sum(t.amount for t in rd["tips"])

        is_admin = user.role == UserRole.ADMIN
        can_edit = is_admin or rd["report"].user_id == user.id
        header_row = ft.Row([
            ft.Column([
                ft.Text(f"Reporte — {shift_name}", size=SUBTITLE_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
                ft.Text(f"Por: {rd['user_name']}", size=SMALL_SIZE, color=TEXT_SECONDARY),
            ], spacing=2, expand=True),
            ft.IconButton(
                icon=ft.Icons.EDIT_OUTLINED,
                icon_color=PRIMARY,
                icon_size=20,
                tooltip="Editar reporte",
                on_click=lambda e, rid=report_id, uid=rd["report"].user_id: report_form_dialog(
                    page, uid, _refresh_reports, report_id=rid
                ),
                visible=can_edit,
            ),
            ft.IconButton(
                icon=ft.Icons.DELETE_OUTLINE,
                icon_color=ERROR,
                icon_size=20,
                tooltip="Eliminar reporte",
                on_click=lambda e, rid=report_id, lbl=f"{rd['user_name']} ({shift_name})": _delete_report(rid, lbl),
                visible=is_admin,
            ),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.START)

        return ft.Container(
            content=ft.Column([
                header_row,
                ft.Divider(height=1, color=DIVIDER_COLOR),
                _section("Contabilidad de Cigarros", ft.Icons.SMOKING_ROOMS, [_build_cigarette_table(rd["cigarettes"])]),
                _section("Lotería y Lotto", ft.Icons.CONFIRMATION_NUMBER, [_build_lottery_table(rd["lottery"])]),
                _section("Cheques Emitidos", ft.Icons.RECEIPT, [
                    ft.Text(f"Total cheques: ${checks_total:,.2f}", size=BODY_SIZE, color=TEXT_PRIMARY,
                            weight=ft.FontWeight.BOLD) if rd["checks"]
                    else ft.Text("Sin cheques", size=SMALL_SIZE, color=TEXT_SECONDARY, italic=True),
                ]),
                _section("Propinas", ft.Icons.VOLUNTEER_ACTIVISM, [
                    ft.Text(f"Propina recibida: ${tips_total:,.2f}", size=BODY_SIZE, color=SUCCESS,
                            weight=ft.FontWeight.BOLD) if rd["tips"]
                    else ft.Text("Sin propinas registradas", size=SMALL_SIZE, color=TEXT_SECONDARY, italic=True),
                ]),
                _section("Productos Especiales", ft.Icons.STAR, [_build_specials_table(rd["specials"])]),
            ], spacing=12),
            padding=16, border_radius=12, bgcolor=ft.Colors.with_opacity(0.03, PRIMARY),
            border=ft.border.all(1, DIVIDER_COLOR),
        )

    def _build_content(d: date, shift: ShiftType | None, uid: int | None = None):
        reports = _load_reports(d, shift, uid)
        if not reports:
            shift_label = ""
            if shift == ShiftType.MORNING:
                shift_label = " (Mañana)"
            elif shift == ShiftType.NIGHT:
                shift_label = " (Noche)"
            return [ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.DESCRIPTION, size=48, color=TEXT_SECONDARY),
                    ft.Text(f"Sin reportes para {d.strftime('%d/%m/%Y')}{shift_label}",
                            size=BODY_SIZE, color=TEXT_SECONDARY),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                alignment=ft.Alignment(0, 0), padding=40,
            )]
        return [_build_report_view(rd) for rd in reports]

    def _get_selected_shift():
        sel = shift_selector.current.selected
        if sel and len(sel) > 0:
            val = list(sel)[0]
            if val == "morning":
                return ShiftType.MORNING
            elif val == "night":
                return ShiftType.NIGHT
        return None

    def _on_date_selected(d: date):
        nonlocal selected_date
        selected_date = d
        content_area.current.controls.clear()
        content_area.current.controls.extend(_build_content(d, _get_selected_shift(), selected_user_id))
        content_area.current.update()

    def _on_shift_change(e):
        content_area.current.controls.clear()
        content_area.current.controls.extend(_build_content(selected_date, _get_selected_shift(), selected_user_id))
        content_area.current.update()

    def _on_user_filter_change(e):
        nonlocal selected_user_id
        val = user_filter_dd.current.value
        selected_user_id = int(val) if val and val != "all" else None
        content_area.current.controls.clear()
        content_area.current.controls.extend(_build_content(selected_date, _get_selected_shift(), selected_user_id))
        content_area.current.update()

    def _refresh_reports():
        content_area.current.controls.clear()
        content_area.current.controls.extend(_build_content(selected_date, _get_selected_shift(), selected_user_id))
        content_area.current.update()

    def _new_report(e):
        report_form_dialog(page, user.id, on_saved=_refresh_reports)

    _dl_picker = ft.FilePicker()
    page.services.append(_dl_picker)

    # ── Scan Report (OCR from image) ──

    _scan_picker = ft.FilePicker()

    def _on_scan_result(e):
        if not e.files:
            return
        file = e.files[0]
        filepath = file.path

        tmp_path = None
        if not filepath:
            if not file.bytes:
                show_toast(page, "No se pudo leer la imagen", is_error=True)
                return
            import tempfile
            import os as _os
            suffix = _os.path.splitext(file.name or "img.jpg")[1] or ".jpg"
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(file.bytes)
                    tmp_path = tmp.name
                filepath = tmp_path
            except Exception as exc:
                show_toast(page, f"Error guardando imagen: {exc}", is_error=True)
                return

        show_toast(page, "Procesando imagen con OCR…")

        try:
            from utils.ocr_scan import parse_report_image
            data = parse_report_image(filepath)
        except RuntimeError as exc:
            _show_ocr_error(str(exc))
            return
        except Exception as exc:
            show_toast(page, f"Error al procesar la imagen: {exc}", is_error=True)
            return
        finally:
            if tmp_path:
                try:
                    import os as _os2
                    _os2.unlink(tmp_path)
                except Exception:
                    pass
        _open_scan_preview(data)

    _scan_picker.on_result = _on_scan_result
    page.services.append(_scan_picker)

    def _show_ocr_error(msg: str):
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(ft.Icons.ERROR, color=ERROR, size=24),
                ft.Text("OCR no disponible", size=SUBTITLE_SIZE,
                        weight=ft.FontWeight.BOLD, color=ERROR),
            ], spacing=8),
            content=ft.Container(
                content=ft.Column([
                    ft.Text(msg, size=BODY_SIZE, color=TEXT_PRIMARY),
                    ft.Container(height=4),
                    ft.Text(
                        "Pasos para activar el escaneo OCR:",
                        size=BODY_SIZE, weight=ft.FontWeight.W_600, color=TEXT_PRIMARY,
                    ),
                    ft.Container(
                        content=ft.Column([
                            ft.Row([ft.Icon(ft.Icons.LOOKS_ONE, color=PRIMARY, size=18),
                                    ft.Text("Descarga Tesseract OCR para Windows:", size=BODY_SIZE)], spacing=8),
                            ft.Text("  https://github.com/UB-Mannheim/tesseract/wiki",
                                    size=SMALL_SIZE, color=ACCENT, italic=True),
                            ft.Row([ft.Icon(ft.Icons.LOOKS_TWO, color=PRIMARY, size=18),
                                    ft.Text("Instálalo con el instalador (acepta defaults)", size=BODY_SIZE)], spacing=8),
                            ft.Row([ft.Icon(ft.Icons.LOOKS_3, color=PRIMARY, size=18),
                                    ft.Text("Reinicia la aplicación", size=BODY_SIZE)], spacing=8),
                        ], spacing=6),
                        padding=ft.padding.only(left=8),
                    ),
                ], spacing=8, tight=True),
                width=460,
            ),
            actions=[
                ft.TextButton(content=ft.Text("Entendido"), on_click=lambda e: page.pop_dialog()),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(dlg)

    def _open_scan_preview(data: dict):
        rows = data["rows"]
        parse_errors = data.get("parse_errors", [])
        raw_text = data.get("raw_text", "")

        preview_controls = []

        if raw_text.strip():
            preview_controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Text("Texto extraído por OCR:", size=SMALL_SIZE,
                                weight=ft.FontWeight.W_500, color=TEXT_SECONDARY),
                        ft.Container(
                            content=ft.Text(
                                raw_text[:800] + ("…" if len(raw_text) > 800 else ""),
                                size=SMALL_SIZE, color=TEXT_SECONDARY, selectable=True,
                            ),
                            bgcolor=ft.Colors.with_opacity(0.04, PRIMARY),
                            border_radius=6,
                            padding=8,
                        ),
                    ], spacing=4),
                    padding=ft.padding.only(bottom=4),
                )
            )
            preview_controls.append(ft.Divider(height=1, color=DIVIDER_COLOR))

        if parse_errors:
            for err in parse_errors:
                preview_controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.WARNING, color=ACCENT, size=14),
                            ft.Text(err, size=SMALL_SIZE, color=ACCENT),
                        ], spacing=6),
                        padding=ft.padding.symmetric(vertical=2),
                    )
                )
            preview_controls.append(ft.Divider(height=1, color=DIVIDER_COLOR))

        if not rows:
            preview_controls.append(
                ft.Text(
                    "No se pudieron extraer productos del reporte.\n"
                    "Asegúrate de que la foto sea nítida y tenga formato: nombre — cantidad.",
                    size=BODY_SIZE, color=TEXT_SECONDARY, italic=True,
                )
            )
        else:
            preview_controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Text("Producto (OCR → Inventario)", size=SMALL_SIZE,
                                weight=ft.FontWeight.BOLD, color=TEXT_SECONDARY, expand=3),
                        ft.Text("Quitar", size=SMALL_SIZE, weight=ft.FontWeight.BOLD,
                                color=TEXT_SECONDARY, expand=1, text_align=ft.TextAlign.CENTER),
                        ft.Text("Actual", size=SMALL_SIZE, weight=ft.FontWeight.BOLD,
                                color=TEXT_SECONDARY, expand=1, text_align=ft.TextAlign.CENTER),
                        ft.Text("Quedaría", size=SMALL_SIZE, weight=ft.FontWeight.BOLD,
                                color=TEXT_SECONDARY, expand=1, text_align=ft.TextAlign.CENTER),
                    ]),
                    padding=ft.padding.symmetric(horizontal=4, vertical=4),
                    bgcolor=ft.Colors.with_opacity(0.05, PRIMARY),
                    border_radius=6,
                )
            )
            for r in rows:
                has_err = bool(r.get("error"))
                row_bg = ft.Colors.with_opacity(0.06, ERROR) if has_err else "transparent"
                remaining_color = (
                    ERROR if (r["remaining"] is not None and r["remaining"] < 0)
                    else SUCCESS if not has_err else TEXT_SECONDARY
                )
                ocr_name = r.get("ocr_name", r["name"])
                name_display = r["name"]
                subtitle = (
                    ft.Text(f"OCR leyó: \"{ocr_name}\"", size=SMALL_SIZE, color=ACCENT, italic=True)
                    if ocr_name.lower() != r["name"].lower() else ft.Container(height=0)
                )
                error_line = (
                    ft.Text(r["error"], size=SMALL_SIZE, color=ERROR, italic=True)
                    if has_err else ft.Container(height=0)
                )
                preview_controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Column([
                                ft.Text(name_display, size=BODY_SIZE,
                                        color=TEXT_PRIMARY if not has_err else ERROR),
                                subtitle,
                                error_line,
                            ], spacing=1, expand=3),
                            ft.Text(str(r["qty_remove"]), size=BODY_SIZE, color=TEXT_PRIMARY,
                                    expand=1, text_align=ft.TextAlign.CENTER,
                                    weight=ft.FontWeight.W_600),
                            ft.Text(
                                str(r["current_stock"]) if r["current_stock"] is not None else "—",
                                size=BODY_SIZE, color=TEXT_SECONDARY, expand=1,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            ft.Text(
                                str(r["remaining"]) if r["remaining"] is not None else "—",
                                size=BODY_SIZE, color=remaining_color, expand=1,
                                text_align=ft.TextAlign.CENTER, weight=ft.FontWeight.W_600,
                            ),
                        ]),
                        padding=ft.padding.symmetric(horizontal=4, vertical=6),
                        bgcolor=row_bg,
                        border_radius=6,
                    )
                )

        valid_rows = [r for r in rows if not r.get("error")]
        has_valid = len(valid_rows) > 0
        error_count = len([r for r in rows if r.get("error")])

        summary_text = ft.Text(
            f"{len(valid_rows)} producto(s) se descontarán del inventario." +
            (f"  {error_count} fila(s) con errores serán ignoradas." if error_count else ""),
            size=SMALL_SIZE, color=TEXT_SECONDARY, italic=True,
        )

        def _confirm(e):
            page.pop_dialog()
            result = apply_scan_report(valid_rows, user.id if hasattr(user, "id") else None)
            log_action(
                user.id if hasattr(user, "id") else None,
                "SCAN_REPORT", "Inventory", None,
                f"{result['applied']} descuentos aplicados desde foto OCR",
            )
            show_toast(page, f"{result['applied']} producto(s) descontados del inventario.", is_success=True)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(ft.Icons.DOCUMENT_SCANNER, color=PRIMARY_DARK, size=24),
                ft.Text("Prevista del Reporte",
                        size=SUBTITLE_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
            ], spacing=8),
            content=ft.Container(
                content=ft.Column([
                    ft.Text(
                        "Revisa los cambios antes de aplicarlos. Los productos con error serán ignorados.",
                        size=SMALL_SIZE, color=TEXT_SECONDARY,
                    ),
                    ft.Divider(height=1, color=DIVIDER_COLOR),
                    ft.Column(preview_controls, spacing=4, scroll=ft.ScrollMode.AUTO),
                    ft.Divider(height=1, color=DIVIDER_COLOR),
                    summary_text,
                ], spacing=10, tight=True),
                width=520,
                height=480,
            ),
            actions=[
                ft.TextButton(content=ft.Text("Cancelar"), on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton(
                    content=ft.Row([
                        ft.Icon(ft.Icons.CHECK_CIRCLE, size=16, color="white"),
                        ft.Text("Aplicar descuentos", color="white", size=BODY_SIZE),
                    ], spacing=6),
                    bgcolor=PRIMARY if has_valid else TEXT_SECONDARY,
                    disabled=not has_valid,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8),
                                         padding=ft.padding.symmetric(horizontal=16, vertical=10)),
                    on_click=_confirm,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(dlg)

    async def _open_scan_dialog():
        await _scan_picker.pick_files(
            dialog_title="Seleccionar foto del reporte",
            allowed_extensions=["jpg", "jpeg", "png", "bmp", "tiff", "tif", "webp"],
            allow_multiple=False,
        )

    async def _download_excel(shift: ShiftType | None, label: str):
        try:
            import os
            data = _load_reports(selected_date, shift, selected_user_id)
            if not data:
                show_toast(page, f"Sin reportes para descargar ({label})", is_error=True)
                return
            path = export_report_excel_bytes(data, selected_date, label)
            with open(path, "rb") as f:
                file_bytes = f.read()
            await _dl_picker.save_file(file_name=os.path.basename(path), src_bytes=file_bytes)
            show_toast(page, f"Reporte '{label}' exportado correctamente", is_success=True)
        except Exception as exc:
            show_toast(page, f"Error al exportar: {exc}", is_error=True)

    def _btn_download(label: str, shift: ShiftType | None, color: str):
        async def _on_click(e, s=shift, l=label):
            await _download_excel(s, l)
        return ft.ElevatedButton(
            content=ft.Row([
                ft.Icon(ft.Icons.DOWNLOAD, size=16, color="white"),
                ft.Text(label, size=SMALL_SIZE, color="white", weight=ft.FontWeight.W_500),
            ], spacing=4, tight=True),
            bgcolor=color,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.padding.symmetric(horizontal=12, vertical=8),
            ),
            on_click=_on_click,
        )

    initial_content = _build_content(selected_date, None)
    cal = calendar_picker(on_date_selected=_on_date_selected, initial_date=selected_date,
                          cal_width=r_calendar_width(page))

    workers = _load_workers()
    user_filter_options = [ft.dropdown.Option(key="all", text="Todos los empleados")]
    for w in workers:
        user_filter_options.append(ft.dropdown.Option(key=str(w.id), text=w.name))

    new_report_btn = ft.ElevatedButton(
        content=ft.Row([
            ft.Icon(ft.Icons.NOTE_ADD, size=18, color="white"),
            ft.Text("Nuevo Reporte", color="white", size=BODY_SIZE, weight=ft.FontWeight.W_500),
        ], spacing=6),
        bgcolor=SUCCESS,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.padding.symmetric(horizontal=16, vertical=10),
        ),
        on_click=_new_report,
    )

    shift_buttons = ft.SegmentedButton(
        ref=shift_selector,
        selected=["all"],
        allow_empty_selection=False,
        allow_multiple_selection=False,
        segments=[
            ft.Segment(value="all", label=ft.Text("Día Completo")),
            ft.Segment(value="morning", label=ft.Text("Mañana")),
            ft.Segment(value="night", label=ft.Text("Noche")),
        ],
        on_change=_on_shift_change,
    )

    mobile = is_mobile(page)
    action_buttons = ft.Row([
        new_report_btn,
        ft.ElevatedButton(
            content=ft.Row([ft.Icon(ft.Icons.DOCUMENT_SCANNER, size=16, color="white"),
                            ft.Text("Escanear Reporte", size=SMALL_SIZE, color="white")], spacing=4),
            bgcolor="#6A1B9A", on_click=lambda e: page.run_task(_open_scan_dialog),
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6),
                                 padding=ft.padding.symmetric(horizontal=12, vertical=8)),
        ),
        _btn_download("Día Completo", None, "#C62828"),
        _btn_download("Mañana", ShiftType.MORNING, "#2E7D32"),
        _btn_download("Noche", ShiftType.NIGHT, "#C62828"),
    ], spacing=8, wrap=True)

    filters_row = ft.Row([
        shift_buttons,
        ft.Dropdown(
            ref=user_filter_dd,
            options=user_filter_options,
            value="all",
            width=200,
            border_color=PRIMARY,
            text_size=BODY_SIZE,
            on_select=_on_user_filter_change,
        ),
    ], spacing=12, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    main_col = ft.Column([
        ft.Row([
            ft.Column([
                ft.Text("Reportes del Día", size=r_font_title(page), weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
                ft.Text("Reportes de turnos con cigarros, lotería, cheques y propinas", size=BODY_SIZE, color=TEXT_SECONDARY),
            ], spacing=4, expand=True),
            action_buttons,
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ft.Container(height=4),
        filters_row,
        ft.Container(height=8),
        ft.Column(initial_content, ref=content_area, spacing=16, scroll=ft.ScrollMode.AUTO, expand=True),
    ], expand=True)

    return ft.Container(
        content=responsive_layout(page, main_col, cal),
        padding=r_padding(page), expand=True,
    )
