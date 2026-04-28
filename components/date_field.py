import flet as ft


def make_date_field(label: str, **kwargs) -> ft.TextField:
    """
    TextField para fechas DD/MM/YYYY con:
    - Slashes permanentes auto-insertados
    - Validación inteligente por posición:
        · Día decenas: solo 0-3
        · Día unidades: si decena=3, solo 0-1 (máximo día 31)
        · Mes decenas: solo 0-1
        · Mes unidades: si decena=1, solo 0-2 (máximo mes 12)
    """
    field = ft.TextField(
        label=label,
        hint_text="DD/MM/YYYY",
        keyboard_type=ft.KeyboardType.NUMBER,
        **kwargs,
    )

    def _on_change(e):
        raw = field.value or ""
        # Extrae solo dígitos
        digits = [c for c in raw if c.isdigit()]

        valid: list[str] = []
        for i, ch in enumerate(digits[:8]):
            if i == 0:
                if ch not in "0123":
                    break
            elif i == 1:
                if valid[0] == "3" and ch not in "01":
                    break
            elif i == 2:
                if ch not in "01":
                    break
            elif i == 3:
                if valid[2] == "1" and ch not in "012":
                    break
            valid.append(ch)

        s = "".join(valid)
        if len(s) > 4:
            formatted = s[:2] + "/" + s[2:4] + "/" + s[4:]
        elif len(s) > 2:
            formatted = s[:2] + "/" + s[2:]
        else:
            formatted = s

        if field.value != formatted:
            field.value = formatted
            field.update()

    field.on_change = _on_change
    return field
