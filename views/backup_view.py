import flet as ft
import os
from datetime import datetime
from utils.backup import create_backup, list_backups, restore_backup, BACKUP_DIR
from utils.toast import show_toast
from components.confirm_dialog import confirm_delete_dialog
from assets.styles import (
    PRIMARY, PRIMARY_DARK, SURFACE, SUCCESS, ERROR, ACCENT,
    TEXT_PRIMARY, TEXT_SECONDARY, SUBTITLE_SIZE, BODY_SIZE, SMALL_SIZE, DIVIDER_COLOR,
)
from utils.responsive import r_padding, r_font_title


def backup_view(page: ft.Page, user):
    """Módulo de Backups: crear, restaurar y eliminar copias de seguridad."""

    backup_list = ft.Ref[ft.Column]()
    backup_count_text = ft.Ref[ft.Text]()

    def _refresh():
        backups = list_backups()
        if backup_count_text.current:
            backup_count_text.current.value = f"{len(backups)} copia(s) disponible(s)"
            backup_count_text.current.update()
        if backup_list.current:
            backup_list.current.controls.clear()
            if not backups:
                backup_list.current.controls.append(
                    ft.Container(
                        content=ft.Column([
                            ft.Icon(ft.Icons.BACKUP, size=48, color=TEXT_SECONDARY),
                            ft.Text("Sin copias de seguridad", size=BODY_SIZE, color=TEXT_SECONDARY),
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                        alignment=ft.Alignment(0, 0), padding=40,
                    )
                )
            else:
                for b in backups:
                    backup_list.current.controls.append(_backup_row(b))
            backup_list.current.update()

    def _do_create(e):
        try:
            path = create_backup(label="manual")
            show_toast(page, f"Backup creado: {os.path.basename(path)}", is_success=True)
            _refresh()
        except Exception as exc:
            show_toast(page, f"Error al crear backup: {exc}", is_error=True)

    def _do_restore(backup_path: str, name: str):
        def _confirm():
            try:
                restore_backup(backup_path)
                show_toast(page, f"Base de datos restaurada desde: {name}", is_success=True)
                _refresh()
            except Exception as exc:
                show_toast(page, f"Error al restaurar: {exc}", is_error=True)
        confirm_delete_dialog(
            page,
            "Restaurar Backup",
            f"¿Restaurar la base de datos desde '{name}'?\n\nSe creará un backup automático del estado actual antes de restaurar.",
            _confirm,
        )

    def _do_delete(backup_path: str, name: str):
        def _confirm():
            try:
                os.remove(backup_path)
                show_toast(page, f"Backup eliminado: {name}", is_success=True)
                _refresh()
            except Exception as exc:
                show_toast(page, f"Error al eliminar: {exc}", is_error=True)
        confirm_delete_dialog(page, "Eliminar Backup", f"¿Eliminar el backup '{name}'?", _confirm)

    def _parse_backup_date(name: str) -> str:
        """Parse timestamp from backup filename like migasapp_20260418_123456_manual.db"""
        try:
            parts = name.replace("migasapp_", "").replace(".db", "").split("_")
            date_str = parts[0]
            time_str = parts[1]
            dt = datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S")
            return dt.strftime("%d/%m/%Y %H:%M:%S")
        except Exception:
            return name

    def _get_label(name: str) -> str:
        try:
            parts = name.replace("migasapp_", "").replace(".db", "").split("_")
            lbl = "_".join(parts[2:]) if len(parts) > 2 else ""
            if lbl == "manual":
                return "Manual"
            if lbl == "auto":
                return "Automático"
            if lbl == "pre_restore":
                return "Pre-restauración"
            return lbl.replace("_", " ").title() if lbl else "—"
        except Exception:
            return "—"

    def _backup_row(b: dict):
        label_color = SUCCESS if "manual" in b["name"] else (ACCENT if "auto" in b["name"] else PRIMARY)
        label_text = _get_label(b["name"])
        date_text = _parse_backup_date(b["name"])

        return ft.Container(
            content=ft.Row([
                ft.Container(
                    content=ft.Icon(ft.Icons.STORAGE, color="white", size=18),
                    bgcolor=label_color, border_radius=8,
                    padding=ft.padding.all(8),
                ),
                ft.Column([
                    ft.Text(b["name"], size=SMALL_SIZE, color=TEXT_PRIMARY,
                            weight=ft.FontWeight.W_500, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Row([
                        ft.Text(date_text, size=SMALL_SIZE, color=TEXT_SECONDARY),
                        ft.Container(
                            content=ft.Text(label_text, size=10, color="white", weight=ft.FontWeight.BOLD),
                            bgcolor=label_color, border_radius=4,
                            padding=ft.padding.symmetric(horizontal=6, vertical=2),
                        ),
                        ft.Text(f"{b['size_mb']:.2f} MB", size=SMALL_SIZE, color=TEXT_SECONDARY),
                    ], spacing=8),
                ], spacing=2, expand=True),
                ft.Row([
                    ft.IconButton(
                        icon=ft.Icons.RESTORE,
                        icon_color=PRIMARY,
                        icon_size=20,
                        tooltip="Restaurar este backup",
                        on_click=lambda e, p=b["path"], n=b["name"]: _do_restore(p, n),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE,
                        icon_color=ERROR,
                        icon_size=20,
                        tooltip="Eliminar este backup",
                        on_click=lambda e, p=b["path"], n=b["name"]: _do_delete(p, n),
                    ),
                ], spacing=0),
            ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.symmetric(horizontal=16, vertical=10),
            border_radius=10,
            bgcolor=SURFACE,
            border=ft.border.all(1, DIVIDER_COLOR),
        )

    initial_backups = list_backups()
    initial_rows = [_backup_row(b) for b in initial_backups] if initial_backups else [
        ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.BACKUP, size=48, color=TEXT_SECONDARY),
                ft.Text("Sin copias de seguridad", size=BODY_SIZE, color=TEXT_SECONDARY),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
            alignment=ft.Alignment(0, 0), padding=40,
        )
    ]

    info_card = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.INFO_OUTLINE, color=PRIMARY, size=20),
                ft.Text("Información de Backups", size=BODY_SIZE, weight=ft.FontWeight.W_600, color=PRIMARY_DARK),
            ], spacing=8),
            ft.Divider(height=1, color=DIVIDER_COLOR),
            ft.Text(
                "• Se crea un backup automático cada vez que la app inicia.\n"
                "• Los backups manuales se guardan con etiqueta 'Manual'.\n"
                "• Al restaurar, se crea primero un backup del estado actual.\n"
                f"• Ubicación: {BACKUP_DIR}\n"
                "• Se conservan las últimas 10 copias automáticamente.",
                size=SMALL_SIZE, color=TEXT_SECONDARY,
            ),
        ], spacing=8),
        padding=16, border_radius=12, bgcolor=SURFACE,
        border=ft.border.all(1, DIVIDER_COLOR),
    )

    main_col = ft.Column([
        ft.Row([
            ft.Column([
                ft.Text("Copias de Seguridad", size=r_font_title(page), weight=ft.FontWeight.BOLD, color=PRIMARY_DARK),
                ft.Text("Gestiona los backups de la base de datos", size=BODY_SIZE, color=TEXT_SECONDARY),
            ], spacing=4, expand=True),
            ft.ElevatedButton(
                content=ft.Row([
                    ft.Icon(ft.Icons.BACKUP, size=18, color="white"),
                    ft.Text("Crear Backup Ahora", color="white", size=BODY_SIZE, weight=ft.FontWeight.W_500),
                ], spacing=6),
                bgcolor=PRIMARY_DARK,
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=8),
                    padding=ft.padding.symmetric(horizontal=16, vertical=10),
                ),
                on_click=_do_create,
            ),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ft.Container(height=4),
        info_card,
        ft.Container(height=4),
        ft.Row([
            ft.Text("Backups disponibles", size=BODY_SIZE, weight=ft.FontWeight.W_600, color=TEXT_PRIMARY, expand=True),
            ft.Text(f"{len(initial_backups)} copia(s) disponible(s)",
                    ref=backup_count_text, size=SMALL_SIZE, color=TEXT_SECONDARY),
        ]),
        ft.Column(initial_rows, ref=backup_list, spacing=8, scroll=ft.ScrollMode.AUTO, expand=True),
    ], expand=True, spacing=12)

    return ft.Container(
        content=main_col,
        padding=r_padding(page),
        expand=True,
    )
