import flet as ft
from datetime import date, datetime
from database.db import get_session
from database.models import (
    Report, ShiftType, CigaretteCount, LotterySale, Check, Tip, SpecialItemReport,
)
from config import DEFAULT_CIGARETTE_BRANDS, DEFAULT_SCRATCH_NAMES, DEFAULT_SPECIAL_ITEMS
from assets.styles import (
    PRIMARY, PRIMARY_DARK, PRIMARY_LIGHT, SURFACE, SUCCESS, ERROR, ACCENT,
    TEXT_PRIMARY, TEXT_SECONDARY, FONT_FAMILY, TITLE_SIZE, SUBTITLE_SIZE, BODY_SIZE, SMALL_SIZE, DIVIDER_COLOR,
)
from utils.responsive import r_dialog_width, r_field_width, is_phone
from utils.toast import show_toast


def report_form_dialog(page: ft.Page, user_id: int, on_saved, report_id: int | None = None):
    """
    Diálogo modal para crear un nuevo reporte de turno.
    Genera las plantillas de cigarros, lotería, cheques, propinas e ítems especiales.
    Las trabajadoras llenan los campos y la app calcula automáticamente.
    """

    # Load existing data for edit mode
    existing_data = None
    if report_id:
        _s = get_session()
        try:
            from sqlalchemy.orm import joinedload as _jl
            _r = (
                _s.query(Report)
                .options(
                    _jl(Report.cigarette_counts),
                    _jl(Report.lottery_sales),
                    _jl(Report.checks),
                    _jl(Report.tips),
                    _jl(Report.special_items),
                )
                .get(report_id)
            )
            if _r:
                existing_data = {
                    "shift": _r.shift,
                    "date": _r.date,
                    "cigarettes": [(_c.brand, _c.boxes_start, _c.boxes_end, _c.sold) for _c in _r.cigarette_counts],
                    "lottery": [(_ls.scratch_name, _ls.amount, _ls.lotto_amount) for _ls in _r.lottery_sales],
                    "checks": [(_ch.description or "", _ch.amount) for _ch in _r.checks],
                    "tip": _r.tips[0].amount if _r.tips else 0,
                    "specials": [(_sp.item_name, _sp.sold, _sp.remaining) for _sp in _r.special_items],
                }
        finally:
            _s.close()

    phone = is_phone(page)

    # --- Shift selector ---
    shift_dropdown = ft.Dropdown(
        label="Turno",
        width=r_field_width(page, 200),
        expand=phone,
        options=[
            ft.dropdown.Option(key="morning", text="Mañana"),
            ft.dropdown.Option(key="night", text="Noche"),
        ],
        value="morning",
        border_color=PRIMARY,
        text_size=BODY_SIZE,
    )

    report_date_text = ft.Text(
        f"Fecha: {date.today().strftime('%d/%m/%Y')}",
        size=BODY_SIZE, color=TEXT_SECONDARY,
    )

    # =====================================================
    # CIGARROS
    # =====================================================
    cig_rows: dict[str, dict[str, ft.TextField]] = {}
    cig_total_label = ft.Ref[ft.Text]()

    def _cig_field(brand, key):
        field = ft.TextField(
            value="0", width=80, text_align=ft.TextAlign.CENTER,
            text_size=SMALL_SIZE, border_color=DIVIDER_COLOR,
            input_filter=ft.NumbersOnlyInputFilter(),
            on_change=lambda e, b=brand: _calc_cig_row(b),
        )
        if brand not in cig_rows:
            cig_rows[brand] = {}
        cig_rows[brand][key] = field
        return field

    def _calc_cig_row(brand):
        row = cig_rows[brand]
        try:
            start = int(row["start"].value or 0)
            end = int(row["end"].value or 0)
            sold = start - end
            if sold < 0:
                sold = 0
            row["sold"].value = str(sold)
            row["sold"].update()
            _calc_cig_total()
        except (ValueError, AttributeError):
            pass

    def _calc_cig_total():
        total = 0
        for brand_data in cig_rows.values():
            try:
                total += int(brand_data["sold"].value or 0)
            except ValueError:
                pass
        if cig_total_label.current:
            cig_total_label.current.value = f"Total vendidos: {total} cajas"
            cig_total_label.current.update()

    def _build_cigarette_section():
        header = ft.Row([
            ft.Text("Marca", size=SMALL_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK, width=150),
            ft.Text("Inicio", size=SMALL_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK, width=80,
                     text_align=ft.TextAlign.CENTER),
            ft.Text("Resto", size=SMALL_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK, width=80,
                     text_align=ft.TextAlign.CENTER),
            ft.Text("Vendidos", size=SMALL_SIZE, weight=ft.FontWeight.BOLD, color=SUCCESS, width=80,
                     text_align=ft.TextAlign.CENTER),
        ], spacing=8)

        rows = [header, ft.Divider(height=1, color=DIVIDER_COLOR)]
        for brand in DEFAULT_CIGARETTE_BRANDS:
            sold_field = _cig_field(brand, "sold")
            sold_field.read_only = True
            sold_field.bgcolor = ft.Colors.with_opacity(0.05, SUCCESS)
            rows.append(ft.Row([
                ft.Text(brand, size=SMALL_SIZE, color=TEXT_PRIMARY, width=150),
                _cig_field(brand, "start"),
                _cig_field(brand, "end"),
                sold_field,
            ], spacing=8))

        rows.append(ft.Divider(height=1, color=DIVIDER_COLOR))
        rows.append(ft.Text("Total vendidos: 0 cajas", ref=cig_total_label,
                            size=BODY_SIZE, weight=ft.FontWeight.BOLD, color=SUCCESS))

        return _form_section("Contabilidad de Cigarros", ft.Icons.SMOKING_ROOMS, rows)

    # =====================================================
    # LOTERÍA + LOTTO
    # =====================================================
    lottery_rows: dict[str, dict[str, ft.TextField]] = {}
    lotto_field = ft.TextField(
        label="Ventas de Lotto ($)", value="0", width=200,
        text_size=BODY_SIZE, border_color=PRIMARY,
        input_filter=ft.InputFilter(regex_string=r"[0-9.]", allow=True),
        on_change=lambda e: _calc_lottery_total(),
    )
    lottery_total_label = ft.Ref[ft.Text]()

    def _lottery_field(name):
        field = ft.TextField(
            value="0", width=120, text_align=ft.TextAlign.CENTER,
            text_size=SMALL_SIZE, border_color=DIVIDER_COLOR,
            input_filter=ft.InputFilter(regex_string=r"[0-9.]", allow=True),
            on_change=lambda e: _calc_lottery_total(),
        )
        lottery_rows[name] = {"amount": field}
        return field

    def _calc_lottery_total():
        total_scratch = 0
        for data in lottery_rows.values():
            try:
                total_scratch += float(data["amount"].value or 0)
            except ValueError:
                pass
        try:
            lotto_val = float(lotto_field.value or 0)
        except ValueError:
            lotto_val = 0

        total = total_scratch + lotto_val
        if lottery_total_label.current:
            lottery_total_label.current.value = (
                f"Scratch: ${total_scratch:,.2f} + Lotto: ${lotto_val:,.2f} = Total: ${total:,.2f}"
            )
            lottery_total_label.current.update()

    def _build_lottery_section():
        header = ft.Row([
            ft.Text("Scratch", size=SMALL_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK, width=150),
            ft.Text("Ventas ($)", size=SMALL_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK, width=120,
                     text_align=ft.TextAlign.CENTER),
        ], spacing=8)

        rows = [header, ft.Divider(height=1, color=DIVIDER_COLOR)]
        for name in DEFAULT_SCRATCH_NAMES:
            rows.append(ft.Row([
                ft.Text(name, size=SMALL_SIZE, color=TEXT_PRIMARY, width=150),
                _lottery_field(name),
            ], spacing=8))

        rows.append(ft.Divider(height=1, color=DIVIDER_COLOR))
        rows.append(ft.Row([
            ft.Text("VENTAS DE LOTTO", size=SMALL_SIZE, weight=ft.FontWeight.BOLD, color=ACCENT, width=150),
            lotto_field,
        ], spacing=8))
        rows.append(ft.Divider(height=1, color=DIVIDER_COLOR))
        rows.append(ft.Text(
            "Scratch: $0.00 + Lotto: $0.00 = Total: $0.00",
            ref=lottery_total_label, size=BODY_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK,
        ))

        return _form_section("Lotería y Lotto", ft.Icons.CONFIRMATION_NUMBER, rows)

    # =====================================================
    # CHEQUES
    # =====================================================
    checks_list = ft.Ref[ft.Column]()
    check_entries: list[dict[str, ft.TextField]] = []
    checks_total_label = ft.Ref[ft.Text]()

    # Pre-populate checks for edit mode
    if existing_data:
        for _desc, _amount in existing_data["checks"]:
            check_entries.append({
                "desc": ft.TextField(
                    label="Descripción", width=250, text_size=SMALL_SIZE,
                    border_color=DIVIDER_COLOR, value=_desc,
                ),
                "amount": ft.TextField(
                    label="Monto ($)", width=120, text_size=SMALL_SIZE,
                    border_color=DIVIDER_COLOR, value=str(_amount),
                    input_filter=ft.InputFilter(regex_string=r"[0-9.]", allow=True),
                    on_change=lambda e: _calc_checks_total(),
                ),
            })

    def _add_check(e=None):
        desc_field = ft.TextField(
            label="Descripción", width=250, text_size=SMALL_SIZE, border_color=DIVIDER_COLOR,
        )
        amount_field = ft.TextField(
            label="Monto ($)", width=120, text_size=SMALL_SIZE, border_color=DIVIDER_COLOR,
            input_filter=ft.InputFilter(regex_string=r"[0-9.]", allow=True),
            on_change=lambda e: _calc_checks_total(),
        )
        idx = len(check_entries)
        check_entries.append({"desc": desc_field, "amount": amount_field})

        def _remove(e, i=idx):
            if i < len(check_entries):
                check_entries.pop(i)
                _rebuild_checks_list()
                _calc_checks_total()

        row = ft.Row([
            desc_field, amount_field,
            ft.IconButton(icon=ft.Icons.DELETE, icon_color=ERROR, icon_size=18, on_click=_remove, tooltip="Eliminar"),
        ], spacing=8)

        if checks_list.current:
            checks_list.current.controls.append(row)
            checks_list.current.update()

    def _rebuild_checks_list():
        if not checks_list.current:
            return
        checks_list.current.controls.clear()
        for i, entry in enumerate(check_entries):
            def _remove(e, idx=i):
                if idx < len(check_entries):
                    check_entries.pop(idx)
                    _rebuild_checks_list()
                    _calc_checks_total()

            checks_list.current.controls.append(ft.Row([
                entry["desc"], entry["amount"],
                ft.IconButton(icon=ft.Icons.DELETE, icon_color=ERROR, icon_size=18, on_click=_remove),
            ], spacing=8))
        checks_list.current.update()

    def _calc_checks_total():
        total = 0
        for entry in check_entries:
            try:
                total += float(entry["amount"].value or 0)
            except ValueError:
                pass
        if checks_total_label.current:
            checks_total_label.current.value = f"Total cheques: ${total:,.2f}"
            checks_total_label.current.update()

    def _build_checks_section():
        initial_rows = []
        for i, entry in enumerate(check_entries):
            def _remove_pre(e, idx=i):
                if idx < len(check_entries):
                    check_entries.pop(idx)
                    _rebuild_checks_list()
                    _calc_checks_total()
            initial_rows.append(ft.Row([
                entry["desc"], entry["amount"],
                ft.IconButton(icon=ft.Icons.DELETE, icon_color=ERROR, icon_size=18,
                              on_click=_remove_pre, tooltip="Eliminar"),
            ], spacing=8))
        return _form_section("Cheques Emitidos", ft.Icons.RECEIPT, [
            ft.Column(initial_rows, ref=checks_list, spacing=6),
            ft.Row([
                ft.ElevatedButton(
                    content=ft.Row([ft.Icon(ft.Icons.ADD, size=16, color="white"),
                                    ft.Text("Agregar Cheque", size=SMALL_SIZE, color="white")], spacing=4),
                    bgcolor=PRIMARY, on_click=_add_check,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6),
                                         padding=ft.padding.symmetric(horizontal=12, vertical=8)),
                ),
                ft.Text("Total cheques: $0.00", ref=checks_total_label,
                        size=BODY_SIZE, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
            ], spacing=16, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ])

    # =====================================================
    # PROPINAS
    # =====================================================
    tip_field = ft.TextField(
        label="Propina recibida ($)", value="0", width=200,
        text_size=BODY_SIZE, border_color=PRIMARY,
        input_filter=ft.InputFilter(regex_string=r"[0-9.]", allow=True),
    )

    def _build_tips_section():
        return _form_section("Propinas", ft.Icons.VOLUNTEER_ACTIVISM, [tip_field])

    # =====================================================
    # PRODUCTOS ESPECIALES
    # =====================================================
    special_fields: dict[str, dict[str, ft.TextField]] = {}

    def _special_field(item, key):
        field = ft.TextField(
            value="0", width=80, text_align=ft.TextAlign.CENTER,
            text_size=SMALL_SIZE, border_color=DIVIDER_COLOR,
            input_filter=ft.NumbersOnlyInputFilter(),
        )
        if item not in special_fields:
            special_fields[item] = {}
        special_fields[item][key] = field
        return field

    def _build_specials_section():
        header = ft.Row([
            ft.Text("Producto", size=SMALL_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK, width=160),
            ft.Text("Vendidos", size=SMALL_SIZE, weight=ft.FontWeight.BOLD, color=SUCCESS, width=80,
                     text_align=ft.TextAlign.CENTER),
            ft.Text("Quedan", size=SMALL_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK, width=80,
                     text_align=ft.TextAlign.CENTER),
        ], spacing=8)

        rows = [header, ft.Divider(height=1, color=DIVIDER_COLOR)]
        for item in DEFAULT_SPECIAL_ITEMS:
            rows.append(ft.Row([
                ft.Text(item, size=SMALL_SIZE, color=TEXT_PRIMARY, width=160),
                _special_field(item, "sold"),
                _special_field(item, "remaining"),
            ], spacing=8))

        return _form_section("Productos Especiales", ft.Icons.STAR, rows)

    # =====================================================
    # SAVE LOGIC
    # =====================================================
    status_text = ft.Text("", size=BODY_SIZE)

    def _save_report(e):
        shift_val = shift_dropdown.value
        if not shift_val:
            status_text.value = "Selecciona un turno"
            status_text.color = ERROR
            status_text.update()
            show_toast(page, "Selecciona un turno", is_error=True)
            return

        shift = ShiftType.MORNING if shift_val == "morning" else ShiftType.NIGHT

        session = get_session()
        try:
            if report_id:
                # Edit mode: clear existing sub-records and reuse the report row
                session.query(CigaretteCount).filter_by(report_id=report_id).delete()
                session.query(LotterySale).filter_by(report_id=report_id).delete()
                session.query(Check).filter_by(report_id=report_id).delete()
                session.query(Tip).filter_by(report_id=report_id).delete()
                session.query(SpecialItemReport).filter_by(report_id=report_id).delete()
                session.flush()
                report = session.query(Report).get(report_id)
            else:
                # Create mode: check for duplicates
                today = date.today()
                existing = session.query(Report).filter_by(
                    user_id=user_id, date=today, shift=shift
                ).first()
                if existing:
                    msg = f"Ya existe un reporte para el turno de {'mañana' if shift_val == 'morning' else 'noche'} hoy"
                    status_text.value = msg
                    status_text.color = ERROR
                    status_text.update()
                    show_toast(page, msg, is_error=True)
                    return

                report = Report(user_id=user_id, date=today, shift=shift)
                session.add(report)
                session.flush()  # Get report.id

            # Save cigarettes
            for brand, fields in cig_rows.items():
                start = int(fields["start"].value or 0)
                end = int(fields["end"].value or 0)
                sold = int(fields["sold"].value or 0)
                if start > 0 or end > 0 or sold > 0:
                    session.add(CigaretteCount(
                        report_id=report.id, brand=brand,
                        boxes_start=start, sold=sold, boxes_end=end,
                    ))

            # Save lottery
            for name, fields in lottery_rows.items():
                amount = float(fields["amount"].value or 0)
                if amount > 0:
                    lotto_amt = 0.0
                    session.add(LotterySale(
                        report_id=report.id, scratch_name=name,
                        amount=amount, lotto_amount=0,
                    ))

            # Save lotto as a separate entry
            lotto_amount = float(lotto_field.value or 0)
            if lotto_amount > 0:
                session.add(LotterySale(
                    report_id=report.id, scratch_name="Lotto",
                    amount=0, lotto_amount=lotto_amount,
                ))

            # Save checks
            for entry in check_entries:
                desc = entry["desc"].value.strip() if entry["desc"].value else ""
                amount = float(entry["amount"].value or 0)
                if amount > 0:
                    session.add(Check(
                        report_id=report.id, description=desc, amount=amount,
                    ))

            # Save tip
            tip_amount = float(tip_field.value or 0)
            if tip_amount > 0:
                session.add(Tip(report_id=report.id, amount=tip_amount))

            # Save special items
            for item, fields in special_fields.items():
                sold = int(fields["sold"].value or 0)
                remaining = int(fields["remaining"].value or 0)
                if sold > 0 or remaining > 0:
                    session.add(SpecialItemReport(
                        report_id=report.id, item_name=item,
                        sold=sold, remaining=remaining,
                    ))

            session.commit()

        except Exception as ex:
            session.rollback()
            status_text.value = f"Error al guardar: {str(ex)}"
            status_text.color = ERROR
            status_text.update()
            show_toast(page, f"Error al guardar: {str(ex)}", is_error=True)
            return
        finally:
            session.close()

        page.pop_dialog()
        show_toast(page, "Reporte actualizado" if report_id else "Reporte guardado", is_success=True)
        on_saved()

    # =====================================================
    # DIALOG
    # =====================================================
    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Row([
            ft.Icon(ft.Icons.EDIT if report_id else ft.Icons.NOTE_ADD, color=PRIMARY_DARK, size=24),
            ft.Text("Editar Reporte" if report_id else "Nuevo Reporte de Turno", size=SUBTITLE_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
        ], spacing=8),
        content=ft.Container(
            content=ft.Column([
                ft.Row([shift_dropdown, report_date_text], spacing=16,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Divider(height=1, color=DIVIDER_COLOR),
                _build_cigarette_section(),
                _build_lottery_section(),
                _build_checks_section(),
                _build_tips_section(),
                _build_specials_section(),
                status_text,
            ], spacing=16, scroll=ft.ScrollMode.AUTO),
            width=r_dialog_width(page, 700),
            height=None if phone else 500,
        ),
        actions=[
            ft.TextButton(content=ft.Text("Cancelar"), on_click=lambda e: page.pop_dialog()),
            ft.ElevatedButton(
                content=ft.Row([ft.Icon(ft.Icons.SAVE, size=18, color="white"),
                                ft.Text("Guardar Reporte", color="white", size=BODY_SIZE)], spacing=6),
                bgcolor=SUCCESS,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8),
                                     padding=ft.padding.symmetric(horizontal=20, vertical=12)),
                on_click=_save_report,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    # Pre-fill field values for edit mode (sections already built, refs not yet set)
    if existing_data:
        shift_dropdown.value = "morning" if existing_data["shift"] == ShiftType.MORNING else "night"
        shift_dropdown.disabled = True
        report_date_text.value = f"Fecha: {existing_data['date'].strftime('%d/%m/%Y')}"
        for _brand, _start, _end, _sold in existing_data["cigarettes"]:
            if _brand in cig_rows:
                cig_rows[_brand]["start"].value = str(_start)
                cig_rows[_brand]["end"].value = str(_end)
                cig_rows[_brand]["sold"].value = str(_sold)
        for _sname, _amt, _lotto_amt in existing_data["lottery"]:
            if _sname == "Lotto":
                lotto_field.value = str(_lotto_amt)
            elif _sname in lottery_rows:
                lottery_rows[_sname]["amount"].value = str(_amt)
        tip_field.value = str(existing_data["tip"]) if existing_data["tip"] else "0"
        for _iname, _isold, _rem in existing_data["specials"]:
            if _iname in special_fields:
                special_fields[_iname]["sold"].value = str(_isold)
                special_fields[_iname]["remaining"].value = str(_rem)

    page.show_dialog(dlg)

    # After dialog rendered (refs populated), refresh total labels
    if existing_data:
        _calc_cig_total()
        _calc_lottery_total()
        _calc_checks_total()


def _form_section(title, icon, controls):
    return ft.Container(
        content=ft.Column([
            ft.Row([ft.Icon(icon, color=PRIMARY_DARK, size=18),
                    ft.Text(title, size=BODY_SIZE, weight=ft.FontWeight.W_600, color=PRIMARY_DARK)], spacing=8),
            ft.Divider(height=1, color=DIVIDER_COLOR),
            *controls,
        ], spacing=6),
        padding=12, border_radius=10,
        bgcolor=SURFACE,
        border=ft.border.all(1, DIVIDER_COLOR),
    )
