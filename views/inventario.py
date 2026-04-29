import flet as ft
import os
from datetime import date, timedelta
from database.db import get_session
from database.models import Product, Category, ProductStatus, UserRole
from components.product_form import product_form_dialog, adjust_stock_dialog
from components.confirm_dialog import confirm_delete_dialog
from assets.styles import (
    PRIMARY, PRIMARY_DARK, SURFACE, SUCCESS, ERROR, ACCENT,
    TEXT_PRIMARY, TEXT_SECONDARY, FONT_FAMILY, TITLE_SIZE, SUBTITLE_SIZE, BODY_SIZE, SMALL_SIZE, DIVIDER_COLOR,
)
from config import LOW_STOCK_THRESHOLD, EXPIRY_ALERT_DAYS
from utils.responsive import is_mobile, responsive_layout, r_padding, r_font_title, r_field_width, r_side_panel_width, is_phone
from utils.toast import show_toast
from utils.export import export_inventory_excel, export_inventory_import_template, import_inventory_from_excel, apply_scan_report
from utils.audit import log_action


def inventario_view(page: ft.Page, user):
    """Módulo de Inventario: categorías, productos, alertas — con CRUD completo."""

    search_field = ft.Ref[ft.TextField]()
    category_filter = ft.Ref[ft.Dropdown]()
    products_list = ft.Ref[ft.Column]()
    alerts_col = ft.Ref[ft.Column]()
    count_text = ft.Ref[ft.Text]()

    # ── data helpers ──

    def _load_categories():
        session = get_session()
        try:
            return session.query(Category).order_by(Category.name).all()
        finally:
            session.close()

    def _load_products(search="", category_id=None):
        session = get_session()
        try:
            q = session.query(Product).join(Category)
            q = q.filter(Product.status == ProductStatus.ACTIVE)
            if search:
                q = q.filter(Product.name.ilike(f"%{search}%"))
            if category_id:
                q = q.filter(Product.category_id == category_id)
            products = q.order_by(Category.name, Product.name).all()
            # Detach from session so we can use them after close
            result = []
            for p in products:
                result.append({
                    "id": p.id,
                    "name": p.name,
                    "category_name": p.category.name,
                    "stock": p.stock,
                    "min_stock": p.min_stock,
                    "price": p.price,
                    "cost": p.cost,
                    "expiry_date": p.expiry_date,
                    "is_consignment": p.is_consignment,
                    "image_path": p.image_path,
                })
            return result
        finally:
            session.close()

    def _load_pending_products():
        session = get_session()
        try:
            pending = session.query(Product).join(Category).filter(
                Product.status == ProductStatus.PENDING
            ).order_by(Product.created_at.desc()).all()
            result = []
            for p in pending:
                result.append({
                    "id": p.id,
                    "name": p.name,
                    "category_name": p.category.name,
                    "stock": p.stock,
                    "price": p.price,
                    "cost": p.cost,
                    "supplier": p.supplier,
                    "arrival_date": p.arrival_date,
                    "expiry_date": p.expiry_date,
                    "is_consignment": p.is_consignment,
                })
            return result
        finally:
            session.close()

    def _load_alerts():
        session = get_session()
        try:
            low_stock = session.query(Product).filter(Product.stock <= Product.min_stock).all()
            alert_date = date.today() + timedelta(days=EXPIRY_ALERT_DAYS)
            expiring = session.query(Product).filter(
                Product.expiry_date.isnot(None),
                Product.expiry_date <= alert_date,
                Product.expiry_date >= date.today(),
            ).all()
            expired = session.query(Product).filter(
                Product.expiry_date.isnot(None),
                Product.expiry_date < date.today(),
            ).all()
            low = [{"name": p.name, "stock": p.stock} for p in low_stock]
            exp_soon = [{"name": p.name, "expiry_date": p.expiry_date} for p in expiring]
            exp_past = [{"name": p.name, "expiry_date": p.expiry_date} for p in expired]
            return low, exp_soon, exp_past
        finally:
            session.close()

    categories = _load_categories()

    # ── CRUD callbacks ──

    def _refresh():
        _refresh_products()
        _refresh_alerts()
        _refresh_pending()

    def _refresh_products():
        cat_val = category_filter.current.value
        cat_id = int(cat_val) if cat_val and cat_val != "all" else None
        search = search_field.current.value or ""
        rows = _build_product_list(search, cat_id)
        products_list.current.controls.clear()
        products_list.current.controls.extend(rows)
        count_text.current.value = f"{len(rows)} productos"
        products_list.current.update()
        count_text.current.update()

    def _refresh_alerts():
        alerts_col.current.controls.clear()
        alerts_col.current.controls.extend(_build_alerts())
        alerts_col.current.update()

    def _refresh_pending():
        if pending_col.current is None:
            return
        items = _build_pending_section()
        pending_col.current.controls.clear()
        pending_col.current.controls.extend(items)
        pending_col.current.update()

    def _add_product(e):
        product_form_dialog(page, on_saved=_refresh)

    _dl_picker = ft.FilePicker()
    page.services.append(_dl_picker)

    # ── Import picker ──
    _import_result_text = ft.Ref[ft.Text]()
    _import_progress = ft.Ref[ft.ProgressRing]()

    def _on_import_result(e):
        if not e.files:
            return
        filepath = e.files[0].path
        if not filepath:
            show_toast(page, "No se pudo leer el archivo", is_error=True)
            return

        if _import_progress.current:
            _import_progress.current.visible = True
            _import_progress.current.update()

        try:
            result = import_inventory_from_excel(filepath)
        except Exception as exc:
            show_toast(page, f"Error al importar: {exc}", is_error=True)
            if _import_progress.current:
                _import_progress.current.visible = False
                _import_progress.current.update()
            return

        if _import_progress.current:
            _import_progress.current.visible = False

        msg_parts = []
        if result["created"]:
            msg_parts.append(f"✅ {result['created']} productos creados")
        if result["updated"]:
            msg_parts.append(f"🔄 {result['updated']} productos actualizados")
        if result["skipped"]:
            msg_parts.append(f"⏭ {result['skipped']} filas omitidas")
        if result["errors"]:
            msg_parts.append(f"❌ {len(result['errors'])} errores")

        summary = "  |  ".join(msg_parts) if msg_parts else "Sin cambios"

        if _import_result_text.current:
            _import_result_text.current.value = summary
            color = ERROR if result["errors"] else SUCCESS
            _import_result_text.current.color = color
            _import_result_text.current.update()

        if result["errors"]:
            show_toast(page,
                       f"Importado con {len(result['errors'])} error(es). Revisa el resumen.",
                       is_error=True)
        else:
            show_toast(page,
                       f"{result['created']} creados, {result['updated']} actualizados.",
                       is_success=True)
        _refresh()

    _import_picker = ft.FilePicker()
    _import_picker.on_result = _on_import_result
    page.services.append(_import_picker)

    def _open_import_dialog():
        nonlocal _import_result_text, _import_progress
        result_label = ft.Text("", size=SMALL_SIZE, ref=_import_result_text)
        progress = ft.ProgressRing(width=18, height=18, stroke_width=2,
                                   visible=False, ref=_import_progress)

        async def _dl_template(e):
            try:
                path = export_inventory_import_template()
                import os as _os
                with open(path, "rb") as f:
                    data = f.read()
                await _dl_picker.save_file(
                    file_name=_os.path.basename(path),
                    src_bytes=data,
                )
                show_toast(page, "Plantilla descargada", is_success=True)
            except Exception as exc:
                show_toast(page, f"Error: {exc}", is_error=True)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(ft.Icons.UPLOAD_FILE, color=PRIMARY_DARK, size=24),
                ft.Text("Importar Inventario desde Excel",
                        size=SUBTITLE_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
            ], spacing=8),
            content=ft.Container(
                content=ft.Column([
                    ft.Text(
                        "Proceso:",
                        size=BODY_SIZE, weight=ft.FontWeight.W_600, color=TEXT_PRIMARY,
                    ),
                    ft.Container(
                        content=ft.Column([
                            ft.Row([ft.Icon(ft.Icons.LOOKS_ONE, color=PRIMARY, size=18),
                                    ft.Text("Descarga la plantilla Excel",
                                            size=BODY_SIZE, color=TEXT_PRIMARY)], spacing=8),
                            ft.Row([ft.Icon(ft.Icons.LOOKS_TWO, color=PRIMARY, size=18),
                                    ft.Text("Llénala con tus productos",
                                            size=BODY_SIZE, color=TEXT_PRIMARY)], spacing=8),
                            ft.Row([ft.Icon(ft.Icons.LOOKS_3, color=PRIMARY, size=18),
                                    ft.Text("Sube el archivo y listo",
                                            size=BODY_SIZE, color=TEXT_PRIMARY)], spacing=8),
                        ], spacing=6),
                        padding=ft.padding.only(left=8),
                    ),
                    ft.Text(
                        "Si el producto ya existe (mismo nombre + categoría), se suma el stock.",
                        size=SMALL_SIZE, color=TEXT_SECONDARY, italic=True,
                    ),
                    ft.Divider(height=1, color=DIVIDER_COLOR),
                    ft.Row([
                        ft.OutlinedButton(
                            content=ft.Row([
                                ft.Icon(ft.Icons.DOWNLOAD, size=16, color=PRIMARY),
                                ft.Text("Descargar Plantilla", size=SMALL_SIZE, color=PRIMARY),
                            ], spacing=4),
                            on_click=_dl_template,
                            style=ft.ButtonStyle(
                                shape=ft.RoundedRectangleBorder(radius=6),
                                side=ft.BorderSide(color=PRIMARY),
                            ),
                        ),
                        ft.ElevatedButton(
                            content=ft.Row([
                                ft.Icon(ft.Icons.UPLOAD, size=16, color="white"),
                                ft.Text("Seleccionar archivo", size=SMALL_SIZE, color="white"),
                            ], spacing=4),
                            bgcolor=PRIMARY,
                            on_click=lambda e: _import_picker.pick_files(
                                dialog_title="Seleccionar plantilla de inventario",
                                allowed_extensions=["xlsx", "xls"],
                                allow_multiple=False,
                            ),
                            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6)),
                        ),
                    ], spacing=12, wrap=True),
                    ft.Row([progress, result_label], spacing=8),
                ], spacing=12, tight=True),
                width=420,
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

    # ── Scan Report (OCR from image) ──

    _scan_picker = ft.FilePicker()

    def _on_scan_result(e):
        if not e.files:
            return
        filepath = e.files[0].path
        if not filepath:
            show_toast(page, "No se pudo leer la imagen", is_error=True)
            return

        # Show loading toast
        show_toast(page, "Procesando imagen con OCR…")

        try:
            from utils.ocr_scan import parse_report_image
            data = parse_report_image(filepath)
        except RuntimeError as exc:
            # OCR engine not available — show detailed error dialog
            _show_ocr_error(str(exc))
            return
        except Exception as exc:
            show_toast(page, f"Error al procesar la imagen: {exc}", is_error=True)
            return
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

        # ── Build preview rows ──
        preview_controls = []

        # Raw OCR text (collapsible hint)
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
            # Table header
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
                # Show OCR name if it differs from matched product
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
            _refresh()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(ft.Icons.DOCUMENT_SCANNER, color=PRIMARY_DARK, size=24),
                ft.Text("Previsualización del Reporte",
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

    def _open_scan_dialog():
        """Open image file picker directly to scan a report photo."""
        _scan_picker.pick_files(
            dialog_title="Seleccionar foto del reporte",
            allowed_extensions=["jpg", "jpeg", "png", "bmp", "tiff", "tif", "webp"],
            allow_multiple=False,
        )

    async def _export_inv(e):
        try:
            import os
            path = export_inventory_excel()
            with open(path, "rb") as f:
                data = f.read()
            await _dl_picker.save_file(
                file_name=os.path.basename(path),
                src_bytes=data,
            )
            show_toast(page, "Inventario exportado a Excel", is_success=True)
        except Exception as exc:
            show_toast(page, f"Error al exportar: {exc}", is_error=True)

    def _edit_product(pid: int):
        product_form_dialog(page, on_saved=_refresh, product_id=pid)

    def _delete_product(pid: int, name: str):
        def _do():
            session = get_session()
            try:
                prod = session.query(Product).get(pid)
                if prod:
                    log_action(user.id if hasattr(user, 'id') else None, "DELETE", "Product", pid, name)
                    session.delete(prod)
                    session.commit()
            finally:
                session.close()
            _refresh()
        confirm_delete_dialog(page, "Eliminar Producto", f"¿Eliminar \"{name}\" del inventario?", _do)

    def _adjust_stock(pid: int, name: str, stock: int):
        adjust_stock_dialog(page, pid, name, stock, on_saved=_refresh)

    is_admin = user.role == UserRole.ADMIN

    def _approve_product(pid: int, name: str):
        from datetime import datetime as _dt
        session = get_session()
        try:
            prod = session.query(Product).get(pid)
            if prod and prod.status == ProductStatus.PENDING:
                prod.status = ProductStatus.ACTIVE
                prod.approved_by_id = user.id if hasattr(user, "id") else None
                prod.approved_at = _dt.now()
                session.commit()
                show_toast(page, f"'{name}' autorizado y agregado al inventario.", is_success=True)
        finally:
            session.close()
        _refresh()

    # ── UI builders ──

    def _pending_card(p):
        today = date.today()
        arrival = p["arrival_date"]
        can_approve = arrival is None or arrival <= today

        arrival_text = arrival.strftime("%d/%m/%Y") if arrival else "No especificada"
        arrival_color = TEXT_SECONDARY
        days_left_text = ""
        if arrival and arrival > today:
            days_left = (arrival - today).days
            arrival_color = ACCENT
            days_left_text = f"  (faltan {days_left} día{'s' if days_left != 1 else ''})"

        approve_btn = ft.ElevatedButton(
            content=ft.Row([
                ft.Icon(ft.Icons.CHECK_CIRCLE, size=16, color="white"),
                ft.Text("Autorizar", size=SMALL_SIZE, color="white"),
            ], spacing=4),
            bgcolor=SUCCESS if can_approve else TEXT_SECONDARY,
            disabled=not can_approve,
            tooltip="Autorizar y agregar al inventario" if can_approve else f"Disponible el {arrival_text}",
            on_click=lambda e, pid=p["id"], nm=p["name"]: _approve_product(pid, nm),
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=6),
                padding=ft.padding.symmetric(horizontal=10, vertical=6),
            ),
        ) if is_admin else ft.Container()

        supplier_row = ft.Row([
            ft.Icon(ft.Icons.BUSINESS, size=14, color=TEXT_SECONDARY),
            ft.Text(p["supplier"] or "Sin proveedor", size=SMALL_SIZE, color=TEXT_SECONDARY),
        ], spacing=4) if p.get("supplier") else ft.Container()

        return ft.Container(
            content=ft.Row([
                ft.Container(
                    content=ft.Text(p["category_name"][:3].upper(), size=10,
                                   color="white", weight=ft.FontWeight.BOLD,
                                   text_align=ft.TextAlign.CENTER),
                    width=36, height=36, border_radius=8,
                    bgcolor=ACCENT, alignment=ft.Alignment(0, 0),
                ),
                ft.Column([
                    ft.Text(p["name"], size=BODY_SIZE, weight=ft.FontWeight.W_500, color=TEXT_PRIMARY),
                    ft.Text(p["category_name"], size=SMALL_SIZE, color=TEXT_SECONDARY),
                    supplier_row,
                ], spacing=2, expand=True),
                ft.Column([
                    ft.Row([
                        ft.Icon(ft.Icons.LOCAL_SHIPPING, size=13, color=arrival_color),
                        ft.Text(f"Llegada: {arrival_text}{days_left_text}",
                                size=SMALL_SIZE, color=arrival_color),
                    ], spacing=4),
                    ft.Text(f"Stock: {p['stock']}  |  ${p['price']:,.2f}",
                            size=SMALL_SIZE, color=TEXT_SECONDARY),
                ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.END),
                approve_btn,
            ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=12, border_radius=10, bgcolor=SURFACE,
            border=ft.border.all(1, ACCENT if not can_approve else DIVIDER_COLOR),
        )

    pending_col = ft.Ref[ft.Column]()

    def _product_row(p):
        stock_color = ERROR if p["stock"] <= p["min_stock"] else TEXT_PRIMARY
        expiry_text = p["expiry_date"].strftime("%d/%m/%Y") if p["expiry_date"] else "—"
        expiry_color = TEXT_SECONDARY
        if p["expiry_date"]:
            days_left = (p["expiry_date"] - date.today()).days
            if days_left < 0:
                expiry_color = ERROR
            elif days_left <= EXPIRY_ALERT_DAYS:
                expiry_color = ACCENT

        margin = float(p["price"] - p["cost"]) if p["price"] and p["cost"] else 0
        margin_color = SUCCESS if margin > 0 else (ERROR if margin < 0 else TEXT_SECONDARY)

        # Product thumbnail or category badge
        has_image = p.get("image_path") and os.path.exists(p["image_path"])
        if has_image:
            thumb = ft.Image(
                src=p["image_path"], width=36, height=36, fit="cover",
                border_radius=8,
            )
        else:
            thumb = ft.Container(
                content=ft.Text(p["category_name"][:3].upper(), size=10, color="white",
                                weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
                width=36, height=36, border_radius=8,
                bgcolor=PRIMARY, alignment=ft.Alignment(0, 0),
            )

        return ft.Container(
            content=ft.Row(
                [
                    thumb,
                    ft.Column([
                        ft.Text(p["name"], size=BODY_SIZE, weight=ft.FontWeight.W_500, color=TEXT_PRIMARY),
                        ft.Text(p["category_name"], size=SMALL_SIZE, color=TEXT_SECONDARY),
                    ], spacing=0, expand=True),
                    ft.Column([
                        ft.Text(f"Stock: {p['stock']}", size=BODY_SIZE, color=stock_color, weight=ft.FontWeight.BOLD),
                        ft.Text(f"Mín: {p['min_stock']}", size=SMALL_SIZE, color=TEXT_SECONDARY),
                    ], spacing=0, width=80, horizontal_alignment=ft.CrossAxisAlignment.END),
                    ft.Column([
                        ft.Text(f"${p['price']:,.2f}", size=BODY_SIZE, color=SUCCESS, weight=ft.FontWeight.BOLD),
                        ft.Text(f"Margen: ${margin:,.2f}", size=SMALL_SIZE, color=margin_color),
                    ], spacing=0, width=110, horizontal_alignment=ft.CrossAxisAlignment.END),
                    ft.Column([
                        ft.Text(expiry_text, size=BODY_SIZE, color=expiry_color),
                    ], width=85, horizontal_alignment=ft.CrossAxisAlignment.END),
                    ft.Text("Consig." if p["is_consignment"] else "", size=SMALL_SIZE, color=ACCENT, width=48),
                    # Action buttons
                    ft.IconButton(ft.Icons.TUNE, icon_size=16, icon_color=PRIMARY, tooltip="Ajustar stock",
                                  on_click=lambda e, pid=p["id"], nm=p["name"], st=p["stock"]: _adjust_stock(pid, nm, st)),
                    ft.IconButton(ft.Icons.EDIT, icon_size=16, icon_color=PRIMARY, tooltip="Editar",
                                  on_click=lambda e, pid=p["id"]: _edit_product(pid)),
                    ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=16, icon_color=ERROR, tooltip="Eliminar",
                                  on_click=lambda e, pid=p["id"], nm=p["name"]: _delete_product(pid, nm)),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.symmetric(horizontal=12, vertical=8),
            border_radius=8,
            bgcolor=SURFACE,
            border=ft.border.all(1, DIVIDER_COLOR),
        )

    def _build_product_list(search="", category_id=None):
        products = _load_products(search, category_id)
        if not products:
            return [ft.Container(
                content=ft.Text("No se encontraron productos", size=BODY_SIZE, color=TEXT_SECONDARY, italic=True),
                padding=20, alignment=ft.Alignment(0, 0),
            )]
        return [_product_row(p) for p in products]

    def _build_pending_section():
        pending = _load_pending_products()
        if not pending:
            return []
        items = [
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.PENDING_ACTIONS, color=ACCENT, size=18),
                    ft.Text(
                        f"Productos pendientes de autorización ({len(pending)})",
                        size=BODY_SIZE, weight=ft.FontWeight.W_600, color=ACCENT,
                    ),
                ], spacing=8),
                padding=ft.padding.only(top=8, bottom=4),
            ),
        ]
        items.extend([_pending_card(p) for p in pending])
        items.append(ft.Divider(height=1, color=DIVIDER_COLOR))
        return items

    def _build_alerts():
        low, expiring, expired = _load_alerts()
        items = []

        for p in expired:
            items.append(ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.ERROR, color=ERROR, size=16),
                    ft.Text(f"VENCIDO: {p['name']} ({p['expiry_date'].strftime('%d/%m')})",
                            size=SMALL_SIZE, color=ERROR, expand=True),
                ], spacing=6),
                padding=ft.padding.symmetric(horizontal=10, vertical=6),
                border_radius=6, bgcolor=ft.Colors.with_opacity(0.1, ERROR),
            ))

        for p in expiring:
            days = (p["expiry_date"] - date.today()).days
            items.append(ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.TIMER, color=ACCENT, size=16),
                    ft.Text(f"Vence en {days}d: {p['name']}", size=SMALL_SIZE, color=ACCENT, expand=True),
                ], spacing=6),
                padding=ft.padding.symmetric(horizontal=10, vertical=6),
                border_radius=6, bgcolor=ft.Colors.with_opacity(0.08, ACCENT),
            ))

        for p in low:
            items.append(ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.WARNING_AMBER, color=PRIMARY, size=16),
                    ft.Text(f"Stock bajo: {p['name']} ({p['stock']} uds)",
                            size=SMALL_SIZE, color=PRIMARY, expand=True),
                ], spacing=6),
                padding=ft.padding.symmetric(horizontal=10, vertical=6),
                border_radius=6, bgcolor=ft.Colors.with_opacity(0.08, PRIMARY),
            ))

        if not items:
            items.append(ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.CHECK_CIRCLE, color=SUCCESS, size=16),
                    ft.Text("Todo en orden", size=SMALL_SIZE, color=TEXT_SECONDARY),
                ], spacing=6),
                padding=ft.padding.symmetric(horizontal=10, vertical=6),
            ))

        return items

    def _on_search(e):
        _refresh_products()

    def _on_category_change(e):
        _refresh_products()

    # ── Layout ──

    cat_options = [ft.dropdown.Option(key="all", text="Todas las categorías")]
    cat_options.extend([ft.dropdown.Option(key=str(c.id), text=c.name) for c in categories])

    header = ft.Row([
        ft.Column([
            ft.Text("Inventario", size=r_font_title(page), weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
            ft.Text("Productos, stock y alertas de vencimiento", size=BODY_SIZE, color=TEXT_SECONDARY),
        ], spacing=4, expand=True),
        ft.ElevatedButton(
            content=ft.Row([ft.Icon(ft.Icons.UPLOAD_FILE, size=16, color="white"),
                            ft.Text("Importar Excel", size=SMALL_SIZE, color="white")], spacing=4),
            bgcolor=PRIMARY, on_click=lambda e: _open_import_dialog(),
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6),
                                 padding=ft.padding.symmetric(horizontal=12, vertical=8)),
        ),
        ft.ElevatedButton(
            content=ft.Row([ft.Icon(ft.Icons.DOCUMENT_SCANNER, size=16, color="white"),
                            ft.Text("Escanear Reporte", size=SMALL_SIZE, color="white")], spacing=4),
            bgcolor="#6A1B9A", on_click=lambda e: _open_scan_dialog(),
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6),
                                 padding=ft.padding.symmetric(horizontal=12, vertical=8)),
        ),
        ft.ElevatedButton(
            content=ft.Row([ft.Icon(ft.Icons.TABLE_CHART, size=16, color="white"),
                            ft.Text("Excel", size=SMALL_SIZE, color="white")], spacing=4),
            bgcolor="#2E7D32", on_click=_export_inv,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6),
                                 padding=ft.padding.symmetric(horizontal=12, vertical=8)),
        ),
        ft.ElevatedButton(
            content=ft.Row([ft.Icon(ft.Icons.ADD, size=16, color="white"),
                            ft.Text("Nuevo Producto", size=SMALL_SIZE, color="white")], spacing=4),
            bgcolor=SUCCESS, on_click=_add_product,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6),
                                 padding=ft.padding.symmetric(horizontal=12, vertical=8)),
        ),
    ])

    ph = is_phone(page)
    filters_row = ft.Row([
        ft.TextField(
            ref=search_field, label="Buscar producto...", prefix_icon=ft.Icons.SEARCH,
            width=r_field_width(page, 300), expand=ph, border_color=PRIMARY, text_size=BODY_SIZE,
            on_change=_on_search,
        ),
        ft.Dropdown(
            ref=category_filter, label="Categoría", width=r_field_width(page, 250), expand=ph,
            options=cat_options, value="all",
            border_color=PRIMARY, text_size=BODY_SIZE,
            on_select=_on_category_change,
        ),
    ], spacing=12)

    initial_products = _build_product_list()
    initial_alerts = _build_alerts()
    initial_pending = _build_pending_section()

    main_col = ft.Column([
        header,
        filters_row,
        ft.Container(height=8),
        ft.Column(initial_pending, ref=pending_col, spacing=6),
        ft.Text(f"{len(initial_products)} productos", ref=count_text, size=SMALL_SIZE, color=TEXT_SECONDARY),
        ft.Column(initial_products, ref=products_list, spacing=6, scroll=ft.ScrollMode.AUTO, expand=True),
    ], expand=True, spacing=12)

    alerts_panel = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.NOTIFICATIONS_ACTIVE, color=PRIMARY_DARK, size=20),
                ft.Text("Alertas", size=BODY_SIZE, weight=ft.FontWeight.W_600, color=TEXT_PRIMARY),
            ], spacing=8),
            ft.Divider(height=1, color=DIVIDER_COLOR),
            ft.Column(initial_alerts, ref=alerts_col, spacing=4, scroll=ft.ScrollMode.AUTO),
        ], spacing=8),
        padding=16, border_radius=12, bgcolor=SURFACE, width=r_side_panel_width(page),
        shadow=ft.BoxShadow(spread_radius=0, blur_radius=8,
                            color=ft.Colors.with_opacity(0.1, "black"), offset=ft.Offset(0, 2)),
    )

    mobile = is_mobile(page)
    return ft.Container(
        content=responsive_layout(page, main_col, alerts_panel),
        padding=r_padding(page), expand=True,
    )
