import flet as ft
import hashlib
from datetime import date
from database.db import get_session
from database.models import User, UserRole, ClockRecord
from components.confirm_dialog import confirm_delete_dialog
from config import APP_SALT, HOURLY_RATE
from utils.responsive import (
    r_padding, r_font_title, r_dialog_width, r_field_width,
    is_phone, responsive_layout,
)
from assets.styles import (
    PRIMARY, PRIMARY_DARK, PRIMARY_LIGHT, SURFACE, SUCCESS, ERROR, ACCENT,
    TEXT_PRIMARY, TEXT_SECONDARY, FONT_FAMILY, TITLE_SIZE, SUBTITLE_SIZE, BODY_SIZE, SMALL_SIZE, DIVIDER_COLOR,
)


def _hash_password(password: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), APP_SALT.encode(), 100_000
    ).hex()


def _worker_profile_view(page: ft.Page, user: User) -> ft.Container:
    """Read-only profile card shown to workers — only their own data."""
    from utils.responsive import r_padding, r_font_title
    from assets.styles import (
        PRIMARY, PRIMARY_DARK, SURFACE, SUCCESS, ERROR, TEXT_PRIMARY, TEXT_SECONDARY,
        BODY_SIZE, SMALL_SIZE, SUBTITLE_SIZE,
    )

    session = get_session()
    try:
        u = session.query(User).get(user.id)
        # Total hours clocked this month
        today = date.today()
        month_start = today.replace(day=1)
        records = session.query(ClockRecord).filter(
            ClockRecord.user_id == user.id,
            ClockRecord.clock_in >= month_start,
            ClockRecord.clock_out.isnot(None),
        ).all()
        total_minutes = sum(
            int((r.clock_out - r.clock_in).total_seconds() // 60) for r in records
        )
        total_hours = total_minutes / 60
        name = u.name
        username = u.username
        role_label = "Administrador" if u.role == UserRole.ADMIN else "Trabajador"
        active_label = "Activo" if u.is_active else "Inactivo"
        active_color = SUCCESS if u.is_active else ERROR
    finally:
        session.close()

    def _info_row(icon, label, value, value_color=TEXT_PRIMARY):
        return ft.Row([
            ft.Icon(icon, size=18, color=PRIMARY),
            ft.Text(label, size=BODY_SIZE, color=TEXT_SECONDARY, width=130),
            ft.Text(value, size=BODY_SIZE, color=value_color, weight=ft.FontWeight.W_500),
        ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    avatar = ft.Container(
        content=ft.Text(
            name[:2].upper(), size=28, color="white",
            weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER,
        ),
        width=72, height=72, border_radius=36,
        bgcolor=PRIMARY, alignment=ft.Alignment(0, 0),
    )

    card = ft.Container(
        content=ft.Column([
            ft.Row([
                avatar,
                ft.Column([
                    ft.Text(name, size=SUBTITLE_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
                    ft.Text(f"@{username}", size=SMALL_SIZE, color=TEXT_SECONDARY),
                    ft.Container(
                        content=ft.Text(active_label, size=SMALL_SIZE, color="white"),
                        bgcolor=active_color, border_radius=12,
                        padding=ft.padding.symmetric(horizontal=10, vertical=2),
                    ),
                ], spacing=4),
            ], spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(height=1, color=DIVIDER_COLOR),
            _info_row(ft.Icons.BADGE, "Rol:", role_label),
            _info_row(ft.Icons.ACCESS_TIME, "Horas este mes:", f"{total_hours:.1f} h"),
            _info_row(ft.Icons.CALENDAR_TODAY, "Fecha:", today.strftime("%d/%m/%Y")),
        ], spacing=14),
        padding=24, border_radius=14, bgcolor=SURFACE,
        shadow=ft.BoxShadow(spread_radius=0, blur_radius=12,
                            color=ft.Colors.with_opacity(0.08, "black"), offset=ft.Offset(0, 2)),
        width=420,
    )

    return ft.Container(
        content=ft.Column([
            ft.Text("Mi Perfil", size=r_font_title(page), weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
            ft.Text("Tu información personal", size=BODY_SIZE, color=TEXT_SECONDARY),
            ft.Container(height=16),
            card,
        ], spacing=6),
        padding=r_padding(page), expand=True,
    )


def empleados_view(page: ft.Page, user: User):
    """Módulo de Empleados: gestión completa para admin; perfil propio para trabajadores."""

    # Workers see only their own profile — no CRUD, no other workers' data
    if user.role != UserRole.ADMIN:
        return _worker_profile_view(page, user)

    employee_list = ft.Ref[ft.Column]()
    search_field = ft.Ref[ft.TextField]()

    # ── data ──

    def _load_employees(search=""):
        session = get_session()
        try:
            q = session.query(User).order_by(User.name)
            if search:
                q = q.filter(User.name.ilike(f"%{search}%") | User.username.ilike(f"%{search}%"))
            users = q.all()
            return [
                {
                    "id": u.id,
                    "name": u.name,
                    "username": u.username,
                    "role": u.role,
                    "clock_code": u.clock_code,
                    "hourly_rate": u.hourly_rate,
                    "is_active": u.is_active,
                }
                for u in users
            ]
        finally:
            session.close()

    def _refresh():
        search = search_field.current.value if search_field.current else ""
        emps = _load_employees(search=search or "")
        employee_list.current.controls.clear()
        for emp in emps:
            employee_list.current.controls.append(_employee_card(emp))
        employee_list.current.update()

    # ── form dialog ──

    def _employee_dialog(emp: dict | None = None):
        ph = is_phone(page)
        editing = emp is not None
        dw = r_dialog_width(page, 400)
        fw = r_field_width(page, 180) if not ph else None

        name_field = ft.TextField(
            label="Nombre completo", value=emp["name"] if editing else "",
            width=fw, border_color=PRIMARY, text_size=BODY_SIZE,
            autofocus=True,
        )
        username_field = ft.TextField(
            label="Usuario (login)", value=emp["username"] if editing else "",
            width=fw, border_color=PRIMARY, text_size=BODY_SIZE,
        )
        password_field = ft.TextField(
            label="Contraseña" + (" (dejar vacío = no cambiar)" if editing else ""),
            password=True, can_reveal_password=True,
            width=fw, border_color=PRIMARY, text_size=BODY_SIZE,
        )
        clock_field = ft.TextField(
            label="Código de fichaje", value=emp["clock_code"] if editing else "",
            width=fw, border_color=PRIMARY, text_size=BODY_SIZE,
            input_filter=ft.NumbersOnlyInputFilter(), max_length=6,
        )
        rate_field = ft.TextField(
            label="Salario por hora ($)", value=str(emp["hourly_rate"]) if editing else str(HOURLY_RATE),
            width=fw, border_color=PRIMARY, text_size=BODY_SIZE,
            input_filter=ft.InputFilter(regex_string=r"[0-9.]"),
        )
        role_dropdown = ft.Dropdown(
            label="Rol",
            options=[
                ft.DropdownOption(key="worker", text="Trabajador"),
                ft.DropdownOption(key="admin", text="Administrador"),
            ],
            value="admin" if (editing and emp["role"] == UserRole.ADMIN) else "worker",
            width=fw, border_color=PRIMARY, text_size=BODY_SIZE,
        )
        is_active_switch = ft.Switch(
            label="Activo",
            value=emp["is_active"] if editing else True,
            active_color=SUCCESS,
        )
        status_text = ft.Text("", size=BODY_SIZE)

        def _save(e):
            name = name_field.value.strip()
            username = username_field.value.strip()
            password = password_field.value.strip()
            clock = clock_field.value.strip()
            rate_str = rate_field.value.strip()
            role_val = role_dropdown.value

            if not name or not username or not clock or not rate_str:
                status_text.value = "Nombre, usuario, código y salario son obligatorios."
                status_text.color = ERROR
                page.update()
                return

            if not editing and not password:
                status_text.value = "La contraseña es obligatoria para nuevos empleados."
                status_text.color = ERROR
                page.update()
                return

            if not clock.isdigit() or not (3 <= len(clock) <= 6):
                status_text.value = "El código de fichaje debe tener entre 3 y 6 dígitos."
                status_text.color = ERROR
                page.update()
                return

            try:
                rate = float(rate_str)
                if rate < 0:
                    raise ValueError
            except ValueError:
                status_text.value = "Salario inválido."
                status_text.color = ERROR
                page.update()
                return

            session = get_session()
            try:
                # Check username uniqueness
                existing_user = session.query(User).filter_by(username=username).first()
                if existing_user and (not editing or existing_user.id != emp["id"]):
                    status_text.value = f"El usuario '{username}' ya existe."
                    status_text.color = ERROR
                    page.update()
                    return

                # Check clock_code uniqueness
                existing_clock = session.query(User).filter_by(clock_code=clock).first()
                if existing_clock and (not editing or existing_clock.id != emp["id"]):
                    status_text.value = f"El código '{clock}' ya está en uso."
                    status_text.color = ERROR
                    page.update()
                    return

                if editing:
                    u = session.query(User).get(emp["id"])
                    u.name = name
                    u.username = username
                    u.clock_code = clock
                    u.hourly_rate = rate
                    u.role = UserRole.ADMIN if role_val == "admin" else UserRole.WORKER
                    u.is_active = is_active_switch.value
                    if password:
                        u.password_hash = _hash_password(password)
                else:
                    new_user = User(
                        name=name,
                        username=username,
                        password_hash=_hash_password(password),
                        role=UserRole.ADMIN if role_val == "admin" else UserRole.WORKER,
                        clock_code=clock,
                        hourly_rate=rate,
                        is_active=True,
                    )
                    session.add(new_user)

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

        title = "Editar Empleado" if editing else "Nuevo Empleado"
        icon = ft.Icons.EDIT if editing else ft.Icons.PERSON_ADD

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(icon, color=PRIMARY, size=24),
                ft.Text(title, size=SUBTITLE_SIZE, weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
            ], spacing=8),
            content=ft.Container(
                content=ft.Column([
                    ft.Row([name_field, username_field], spacing=12),
                    ft.Row([password_field, clock_field], spacing=12),
                    ft.Row([rate_field, role_dropdown], spacing=12),
                    is_active_switch if editing else ft.Container(),
                    status_text,
                ], spacing=14, scroll=ft.ScrollMode.AUTO),
                width=dw,
                height=None if ph else 320,
            ),
            actions=[
                ft.TextButton(content=ft.Text("Cancelar"), on_click=lambda e: page.pop_dialog()),
                ft.ElevatedButton(
                    content=ft.Row([
                        ft.Icon(ft.Icons.SAVE, size=18, color="white"),
                        ft.Text("Guardar", color="white", size=BODY_SIZE),
                    ], spacing=6),
                    bgcolor=SUCCESS,
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=8),
                        padding=ft.padding.symmetric(horizontal=20, vertical=12),
                    ),
                    on_click=_save,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(dlg)

    # ── toggle active ──

    def _toggle_active(emp: dict):
        action = "desactivar" if emp["is_active"] else "activar"
        title = f"{'Desactivar' if emp['is_active'] else 'Activar'} Empleado"
        msg = f"¿Deseas {action} a {emp['name']}?"

        def _do():
            session = get_session()
            try:
                u = session.query(User).get(emp["id"])
                u.is_active = not u.is_active
                session.commit()
            finally:
                session.close()
            _refresh()

        confirm_delete_dialog(page, title, msg, _do)

    # ── delete ──

    def _delete_employee(emp: dict):
        def _do():
            session = get_session()
            try:
                u = session.query(User).get(emp["id"])
                if u:
                    session.delete(u)
                    session.commit()
            finally:
                session.close()
            _refresh()

        confirm_delete_dialog(
            page,
            "Eliminar Empleado",
            f"¿Eliminar permanentemente a {emp['name']}? Esta acción no se puede deshacer.",
            _do,
        )

    # ── card ──

    def _employee_card(emp: dict) -> ft.Container:
        phone = is_phone(page)
        role_label = "Admin" if emp["role"] == UserRole.ADMIN else "Trabajador"
        role_color = ACCENT if emp["role"] == UserRole.ADMIN else PRIMARY
        active_color = SUCCESS if emp["is_active"] else ERROR
        active_label = "Activo" if emp["is_active"] else "Inactivo"

        is_admin_user = user.role == UserRole.ADMIN

        # Quick salary adjust buttons (admin only)
        salary_row = ft.Row([
            ft.Text(f"${emp['hourly_rate']:.2f}/h", size=SMALL_SIZE, color=TEXT_SECONDARY),
            ft.IconButton(
                icon=ft.Icons.REMOVE_CIRCLE_OUTLINE, icon_color=ERROR,
                tooltip="Bajar salario $1", icon_size=18,
                on_click=lambda e, em=emp: _adjust_salary(em, -1.0),
            ) if is_admin_user else ft.Container(),
            ft.IconButton(
                icon=ft.Icons.ADD_CIRCLE_OUTLINE, icon_color=SUCCESS,
                tooltip="Subir salario $1", icon_size=18,
                on_click=lambda e, em=emp: _adjust_salary(em, +1.0),
            ) if is_admin_user else ft.Container(),
        ], spacing=2, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        info_col = ft.Column([
            ft.Row([
                ft.Text(emp["name"], size=BODY_SIZE, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                ft.Container(
                    content=ft.Text(role_label, size=SMALL_SIZE, color="white"),
                    bgcolor=role_color, border_radius=12,
                    padding=ft.padding.symmetric(horizontal=8, vertical=2),
                ),
                ft.Container(
                    content=ft.Text(active_label, size=SMALL_SIZE, color="white"),
                    bgcolor=active_color, border_radius=12,
                    padding=ft.padding.symmetric(horizontal=8, vertical=2),
                ),
            ], spacing=8, wrap=True),
            ft.Text(
                f"@{emp['username']}  ·  Código: {emp['clock_code']}",
                size=SMALL_SIZE, color=TEXT_SECONDARY,
            ),
            salary_row,
        ], spacing=4)

        actions_row = ft.Row([
            ft.IconButton(
                icon=ft.Icons.EDIT, icon_color=PRIMARY, tooltip="Editar",
                on_click=lambda e, em=emp: _employee_dialog(em),
            ) if is_admin_user else ft.Container(),
            ft.IconButton(
                icon=ft.Icons.TOGGLE_ON if emp["is_active"] else ft.Icons.TOGGLE_OFF,
                icon_color=SUCCESS if emp["is_active"] else TEXT_SECONDARY,
                tooltip="Desactivar" if emp["is_active"] else "Activar",
                on_click=lambda e, em=emp: _toggle_active(em),
            ) if is_admin_user else ft.Container(),
            ft.IconButton(
                icon=ft.Icons.DELETE_OUTLINE, icon_color=ERROR, tooltip="Eliminar",
                on_click=lambda e, em=emp: _delete_employee(em),
            ) if is_admin_user else ft.Container(),
        ], spacing=0)

        return ft.Container(
            content=ft.Row(
                [info_col, ft.Container(expand=True), actions_row],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                wrap=phone,
            ),
            padding=ft.padding.symmetric(horizontal=16, vertical=12),
            border_radius=10,
            bgcolor=SURFACE if emp["is_active"] else ft.Colors.with_opacity(0.04, "black"),
            border=ft.border.all(1, DIVIDER_COLOR if emp["is_active"] else ERROR),
            margin=ft.margin.only(bottom=8),
            shadow=ft.BoxShadow(spread_radius=0, blur_radius=4,
                                color=ft.Colors.with_opacity(0.06, "black"), offset=ft.Offset(0, 1)),
        )

    # ── salary quick adjust ──

    def _adjust_salary(emp: dict, delta: float):
        session = get_session()
        try:
            u = session.query(User).get(emp["id"])
            new_rate = max(0.0, round(u.hourly_rate + delta, 2))
            u.hourly_rate = new_rate
            session.commit()
        finally:
            session.close()
        _refresh()

    # ── build ──

    employees = _load_employees()
    is_admin = user.role == UserRole.ADMIN
    ph = is_phone(page)

    header_row = ft.Row([
        ft.Column([
            ft.Text("Empleados", size=r_font_title(page), weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
            ft.Text(
                "Gestión de trabajadores y administradores" if is_admin else "Lista de empleados",
                size=BODY_SIZE, color=TEXT_SECONDARY,
            ),
        ], spacing=2, expand=True),
        ft.ElevatedButton(
            content=ft.Row([
                ft.Icon(ft.Icons.PERSON_ADD, size=18, color="white"),
                ft.Text("Nuevo Empleado", color="white", size=BODY_SIZE),
            ], spacing=8),
            bgcolor=PRIMARY,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.padding.symmetric(horizontal=20, vertical=14),
            ),
            on_click=lambda e: _employee_dialog(),
        ) if is_admin else ft.Container(),
    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
       vertical_alignment=ft.CrossAxisAlignment.CENTER)

    list_col = ft.Column(
        [_employee_card(emp) for emp in employees],
        ref=employee_list,
        spacing=0,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    emp_search = ft.TextField(
        ref=search_field,
        label="Buscar empleado…",
        prefix_icon=ft.Icons.SEARCH,
        width=r_field_width(page, 300),
        expand=ph,
        border_color=PRIMARY,
        text_size=BODY_SIZE,
        on_change=lambda e: _refresh(),
    )

    main_col = ft.Column([
        header_row,
        emp_search,
        ft.Divider(height=20, color=DIVIDER_COLOR),
        list_col,
    ], expand=True)

    return ft.Container(
        content=main_col,
        padding=r_padding(page),
        expand=True,
    )
