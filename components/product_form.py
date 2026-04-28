import flet as ft
import os
import shutil
from datetime import date
from database.db import get_session
from database.models import Product, Category, ProductStatus
from config import DATA_DIR
from assets.styles import (
    PRIMARY, PRIMARY_DARK, SURFACE, SUCCESS, ERROR, ACCENT,
    TEXT_PRIMARY, TEXT_SECONDARY, SUBTITLE_SIZE, BODY_SIZE, SMALL_SIZE, DIVIDER_COLOR,
)
from utils.responsive import r_dialog_width, r_field_width, is_phone

IMAGES_DIR = os.path.join(DATA_DIR, "product_images")
os.makedirs(IMAGES_DIR, exist_ok=True)


def product_form_dialog(page: ft.Page, on_saved, product_id: int | None = None):
    """Diálogo para agregar o editar un producto."""

    session = get_session()
    try:
        categories = session.query(Category).order_by(Category.name).all()
        cat_options = [ft.dropdown.Option(key=str(c.id), text=c.name) for c in categories]

        existing = None
        if product_id:
            existing = session.query(Product).get(product_id)
    finally:
        session.close()

    phone = is_phone(page)
    fw_lg = r_field_width(page, 400)
    fw_md = r_field_width(page, 250)
    fw_sm = r_field_width(page, 120)
    fw_price = r_field_width(page, 140)
    fw_exp = r_field_width(page, 200)
    dw = r_dialog_width(page, 460)

    name_field = ft.TextField(
        label="Nombre del producto",
        width=fw_lg,
        expand=phone,
        text_size=BODY_SIZE,
        border_color=PRIMARY,
        autofocus=True,
        value=existing.name if existing else "",
    )

    category_dd = ft.Dropdown(
        label="Categoría",
        width=fw_md,
        expand=phone,
        options=cat_options,
        value=str(existing.category_id) if existing else (cat_options[0].key if cat_options else None),
        border_color=PRIMARY,
        text_size=BODY_SIZE,
    )

    stock_field = ft.TextField(
        label="Stock actual",
        width=fw_sm,
        expand=phone,
        text_size=BODY_SIZE,
        border_color=PRIMARY,
        input_filter=ft.InputFilter(regex_string=r"[0-9]", allow=True),
        value=str(existing.stock) if existing else "0",
    )

    min_stock_field = ft.TextField(
        label="Stock mínimo",
        width=fw_sm,
        expand=phone,
        text_size=BODY_SIZE,
        border_color=PRIMARY,
        input_filter=ft.InputFilter(regex_string=r"[0-9]", allow=True),
        value=str(existing.min_stock) if existing else "2",
    )

    price_field = ft.TextField(
        label="Precio venta ($)",
        width=fw_price,
        expand=phone,
        text_size=BODY_SIZE,
        border_color=PRIMARY,
        prefix_icon=ft.Icons.ATTACH_MONEY,
        input_filter=ft.InputFilter(regex_string=r"[0-9.]", allow=True),
        value=f"{existing.price:.2f}" if existing else "",
    )

    cost_field = ft.TextField(
        label="Costo ($)",
        width=fw_price,
        expand=phone,
        text_size=BODY_SIZE,
        border_color=PRIMARY,
        prefix_icon=ft.Icons.ATTACH_MONEY,
        input_filter=ft.InputFilter(regex_string=r"[0-9.]", allow=True),
        value=f"{existing.cost:.2f}" if existing else "",
    )

    expiry_field = ft.TextField(
        label="Vencimiento (DD/MM/YYYY)",
        width=fw_exp,
        expand=phone,
        text_size=BODY_SIZE,
        border_color=PRIMARY,
        hint_text="ej: 15/06/2026",
        value=existing.expiry_date.strftime("%d/%m/%Y") if existing and existing.expiry_date else "",
    )

    supplier_field = ft.TextField(
        label="Compañía / Proveedor",
        width=fw_lg,
        expand=phone,
        text_size=BODY_SIZE,
        border_color=PRIMARY,
        prefix_icon=ft.Icons.BUSINESS,
        hint_text="ej: Distribuidora ABC",
        value=existing.supplier if existing and existing.supplier else "",
    )

    arrival_field = ft.TextField(
        label="Fecha de llegada (DD/MM/YYYY)",
        width=fw_exp,
        expand=phone,
        text_size=BODY_SIZE,
        border_color=PRIMARY,
        hint_text="ej: 28/04/2026",
        value=existing.arrival_date.strftime("%d/%m/%Y") if existing and existing.arrival_date else "",
    )

    is_consignment = ft.Checkbox(
        label="Producto en consignación",
        value=existing.is_consignment if existing else False,
    )

    # ── Image picker ──
    _selected_image_path: list[str | None] = [existing.image_path if existing else None]

    image_preview = ft.Image(
        src=existing.image_path if existing and existing.image_path and os.path.exists(existing.image_path) else "",
        width=100, height=100, fit="cover", border_radius=8,
        visible=bool(existing and existing.image_path and os.path.exists(existing.image_path)),
    )

    image_name_text = ft.Text(
        os.path.basename(existing.image_path) if existing and existing.image_path else "Sin imagen",
        size=SMALL_SIZE, color=TEXT_SECONDARY, width=150, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
    )

    file_picker = ft.FilePicker()
    page.services.append(file_picker)

    async def _pick_image(e):
        files = await file_picker.pick_files(
            dialog_title="Seleccionar imagen del producto",
            allowed_extensions=["png", "jpg", "jpeg", "gif", "webp", "bmp"],
            allow_multiple=False,
            with_data=True,
        )
        if not files:
            return
        f = files[0]
        import time
        ext = os.path.splitext(f.name)[1].lower() or ".jpg"
        dest_name = f"prod_{int(time.time())}_{f.name}"
        dest = os.path.join(IMAGES_DIR, dest_name)
        try:
            if f.path and os.path.exists(f.path):
                # Desktop mode: copy from local path
                shutil.copy2(f.path, dest)
            elif f.bytes:
                # Web mode: write bytes directly
                with open(dest, "wb") as fp:
                    fp.write(f.bytes)
            else:
                return
            _selected_image_path[0] = dest
            image_preview.src = dest
            image_preview.visible = True
            image_name_text.value = f.name
            page.update()
        except Exception:
            pass

    def _remove_image(e):
        _selected_image_path[0] = None
        image_preview.visible = False
        image_name_text.value = "Sin imagen"
        page.update()

    image_section = ft.Row([
        image_preview,
        ft.Column([
            image_name_text,
            ft.Row([
                ft.OutlinedButton("Seleccionar foto", icon=ft.Icons.CAMERA_ALT, on_click=_pick_image),
                ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=18, icon_color=ERROR,
                              tooltip="Quitar imagen", on_click=_remove_image),
            ], spacing=4),
        ], spacing=4),
    ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    status_text = ft.Text("", size=BODY_SIZE)

    def _save(e):
        name = name_field.value.strip() if name_field.value else ""
        if not name:
            status_text.value = "Escribe el nombre del producto"
            status_text.color = ERROR
            page.update()
            return

        if not category_dd.value:
            status_text.value = "Selecciona una categoría"
            status_text.color = ERROR
            page.update()
            return

        try:
            price = float(price_field.value or 0)
        except ValueError:
            price = 0.0

        try:
            cost = float(cost_field.value or 0)
        except ValueError:
            cost = 0.0

        stock = int(stock_field.value or 0)
        min_stock = int(min_stock_field.value or 2)

        expiry = None
        exp_val = expiry_field.value.strip() if expiry_field.value else ""
        if exp_val:
            try:
                parts = exp_val.split("/")
                expiry = date(int(parts[2]), int(parts[1]), int(parts[0]))
            except (ValueError, IndexError):
                status_text.value = "Fecha de vencimiento inválida. Formato: DD/MM/YYYY"
                status_text.color = ERROR
                page.update()
                return

        arrival = None
        arr_val = arrival_field.value.strip() if arrival_field.value else ""
        if arr_val:
            try:
                parts = arr_val.split("/")
                arrival = date(int(parts[2]), int(parts[1]), int(parts[0]))
            except (ValueError, IndexError):
                status_text.value = "Fecha de llegada inválida. Formato: DD/MM/YYYY"
                status_text.color = ERROR
                page.update()
                return

        supplier = supplier_field.value.strip() if supplier_field.value else None

        # Image is already saved to IMAGES_DIR by _pick_image; just use the stored path
        saved_image_path = _selected_image_path[0]

        session = get_session()
        try:
            if product_id:
                prod = session.query(Product).get(product_id)
                prod.name = name
                prod.category_id = int(category_dd.value)
                prod.stock = stock
                prod.min_stock = min_stock
                prod.price = price
                prod.cost = cost
                prod.expiry_date = expiry
                prod.arrival_date = arrival
                prod.supplier = supplier
                prod.is_consignment = is_consignment.value
                prod.image_path = saved_image_path
            else:
                prod = Product(
                    name=name,
                    category_id=int(category_dd.value),
                    stock=stock,
                    min_stock=min_stock,
                    price=price,
                    cost=cost,
                    expiry_date=expiry,
                    arrival_date=arrival,
                    supplier=supplier,
                    is_consignment=is_consignment.value,
                    image_path=saved_image_path,
                    status=ProductStatus.PENDING,
                )
                session.add(prod)
            session.commit()
            page.pop_dialog()
            on_saved()
        except Exception as ex:
            session.rollback()
            status_text.value = f"Error: {str(ex)}"
            status_text.color = ERROR
            page.update()
        finally:
            session.close()

    title_text = "Editar Producto" if product_id else "Nuevo Producto"

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Row([
            ft.Icon(ft.Icons.INVENTORY_2, color=PRIMARY, size=24),
            ft.Text(title_text, size=SUBTITLE_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
        ], spacing=8),
        content=ft.Container(
            content=ft.Column([
                name_field,
                ft.Row([category_dd, is_consignment], spacing=16,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([stock_field, min_stock_field], spacing=12),
                ft.Row([price_field, cost_field], spacing=12),
                ft.Row([expiry_field, arrival_field], spacing=12),
                supplier_field,
                ft.Divider(height=1, color=DIVIDER_COLOR),
                ft.Text("Foto del producto", size=BODY_SIZE, weight=ft.FontWeight.W_500, color=TEXT_PRIMARY),
                image_section,
                status_text,
            ], spacing=14, scroll=ft.ScrollMode.AUTO),
            width=dw,
            height=None if phone else 420,
        ),
        actions=[
            ft.TextButton(content=ft.Text("Cancelar"), on_click=lambda e: page.pop_dialog()),
            ft.ElevatedButton(
                content=ft.Row([ft.Icon(ft.Icons.SAVE, size=18, color="white"),
                                ft.Text("Guardar", color="white", size=BODY_SIZE)], spacing=6),
                bgcolor=SUCCESS,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8),
                                     padding=ft.padding.symmetric(horizontal=20, vertical=12)),
                on_click=_save,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    page.show_dialog(dlg)


def adjust_stock_dialog(page: ft.Page, product_id: int, product_name: str, current_stock: int, on_saved):
    """Diálogo rápido para ajustar stock (+/-)."""

    qty_field = ft.TextField(
        label="Cantidad",
        width=120,
        text_size=BODY_SIZE,
        border_color=PRIMARY,
        input_filter=ft.InputFilter(regex_string=r"[0-9]", allow=True),
        autofocus=True,
        value="1",
    )

    mode = ft.RadioGroup(
        content=ft.Row([
            ft.Radio(value="add", label="Agregar"),
            ft.Radio(value="remove", label="Restar"),
        ]),
        value="add",
    )

    preview_text = ft.Text(f"Stock actual: {current_stock}", size=BODY_SIZE, color=TEXT_SECONDARY)
    status_text = ft.Text("", size=BODY_SIZE)

    def _save(e):
        try:
            qty = int(qty_field.value or 0)
        except ValueError:
            status_text.value = "Cantidad inválida"
            status_text.color = ERROR
            page.update()
            return

        if qty <= 0:
            status_text.value = "Cantidad debe ser mayor a 0"
            status_text.color = ERROR
            page.update()
            return

        session = get_session()
        try:
            prod = session.query(Product).get(product_id)
            if mode.value == "add":
                prod.stock += qty
            else:
                prod.stock = max(0, prod.stock - qty)
            session.commit()
            page.pop_dialog()
            on_saved()
        except Exception as ex:
            session.rollback()
            status_text.value = f"Error: {str(ex)}"
            status_text.color = ERROR
            page.update()
        finally:
            session.close()

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Row([
            ft.Icon(ft.Icons.TUNE, color=PRIMARY, size=24),
            ft.Text(f"Ajustar Stock", size=SUBTITLE_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
        ], spacing=8),
        content=ft.Container(
            content=ft.Column([
                ft.Text(product_name, size=BODY_SIZE, weight=ft.FontWeight.W_600, color=TEXT_PRIMARY),
                preview_text,
                ft.Divider(height=1, color=DIVIDER_COLOR),
                mode,
                qty_field,
                status_text,
            ], spacing=12),
            width=r_dialog_width(page, 300),
            height=None if is_phone(page) else 220,
        ),
        actions=[
            ft.TextButton(content=ft.Text("Cancelar"), on_click=lambda e: page.pop_dialog()),
            ft.ElevatedButton(
                content=ft.Row([ft.Icon(ft.Icons.CHECK, size=18, color="white"),
                                ft.Text("Aplicar", color="white", size=BODY_SIZE)], spacing=6),
                bgcolor=PRIMARY,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8),
                                     padding=ft.padding.symmetric(horizontal=20, vertical=12)),
                on_click=_save,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    page.show_dialog(dlg)
