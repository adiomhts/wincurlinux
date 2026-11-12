# Windows to Linux / GNOME Cursor Converter & Themes

Скрипт для конвертации кастомных Windows-курсоров (`.cur`, `.ani`, `Install.inf`) в формат тем курсоров Linux / GNOME / X11 / Wayland.

## Особенности конвертера (`win_to_linux_cur.py`):
- Нативный парсинг 32-битного RGBA DIB: сохраняет полный 8-битный альфа-канал без затемнения краёв и артефактов тени.
- Корректная обработка анимированных `.ani` курсоров (RIFF ACON) со всеми кадрами и задержками.
- Мультиразмерность (`24, 28, 32, 40, 48, 64`) с масштабированием Lanczos и адаптацией под размеры GNOME.
- Чтение `Install.inf` для правильной расстановки ролей и всех необходимых симлинков под X11 / Wayland.

## Использование скрипта:
```bash
# Требования (обычно уже стоят в системе):
sudo apt install x11-apps imagemagick

# Конвертация:
./win_to_linux_cur.py wincur -o ~/.icons
```


Применение темы:
```bash
gsettings set org.gnome.desktop.interface cursor-theme "dark"
# или
gsettings set org.gnome.desktop.interface cursor-theme "light"
```
