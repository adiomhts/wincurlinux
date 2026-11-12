#!/usr/bin/env python3
"""
Windows Cursor (.cur, .ani) to Linux / X11 Cursor Theme Converter.
Supports GNOME, KDE, XFCE and other X11/Wayland desktop environments.
"""

import os
import sys
import struct
import shutil
import zlib
import tempfile
import subprocess
import argparse
from pathlib import Path


# Mapping from Windows cursor keys / roles to Linux standard cursor names.
CURSOR_ROLE_MAPPING = {
    "pointer": {
        "primary": "left_ptr",
        "aliases": [
            "default", "arrow", "top_left_arrow", "left-arrow",
            "size-default", "size_default"
        ]
    },
    "help": {
        "primary": "help",
        "aliases": [
            "question_arrow", "whats_this", "d9ce0ab605698f320427677b458ad60b",
            "5c6cd98b3f3ebcb1f9c7f1c204630408"
        ]
    },
    "working": {
        "primary": "left_ptr_watch",
        "aliases": [
            "progress", "08e8e1c95fe2fc01f976f1e063a24ccd",
            "3ecb610c1bf2410f44200f48c40d3599",
            "00000000000000020006000e7e9ffc3f"
        ]
    },
    "busy": {
        "primary": "wait",
        "aliases": [
            "watch"
        ]
    },
    "precision": {
        "primary": "crosshair",
        "aliases": [
            "cross", "cross_reverse", "diamond_cross", "tcross"
        ]
    },
    "beam": {
        "primary": "xterm",
        "aliases": [
            "text", "ibeam"
        ]
    },
    "handwriting": {
        "primary": "pencil",
        "aliases": [
            "draft", "write", "pencil-alt"
        ]
    },
    "unavailable": {
        "primary": "not-allowed",
        "aliases": [
            "crossed_circle", "forbidden", "no-drop", "circle",
            "03b6e0fcb3499374a867c041f52298f0"
        ]
    },
    "vert": {
        "primary": "ns-resize",
        "aliases": [
            "v_double_arrow", "sb_v_double_arrow", "n-resize", "s-resize",
            "top_side", "bottom_side", "col-resize", "row-resize",
            "size_ver", "size-ver", "double_arrow", "00008160000006810000408080010102",
            "2870a09082c103050810ffdffffe0204"
        ]
    },
    "horz": {
        "primary": "ew-resize",
        "aliases": [
            "h_double_arrow", "sb_h_double_arrow", "e-resize", "w-resize",
            "left_side", "right_side", "size_hor", "size-hor",
            "028006030e0e7ebffc7f7070c0600140", "14fef782d02440884392942c1120523"
        ]
    },
    "dgn1": {
        "primary": "nwse-resize",
        "aliases": [
            "bd_double_arrow", "nw-resize", "se-resize",
            "top_left_corner", "bottom_right_corner",
            "c7088f0f3e6c8088236ef8e1e3e70000", "size_fdiag", "size-fdiag"
        ]
    },
    "dgn2": {
        "primary": "nesw-resize",
        "aliases": [
            "fd_double_arrow", "ne-resize", "sw-resize",
            "top_right_corner", "bottom_left_corner",
            "50585d75b494802d0151028115016902", "fcf1c3c7cd4491d801f1e1c78f100822",
            "size_bdiag", "size-bdiag"
        ]
    },
    "move": {
        "primary": "fleur",
        "aliases": [
            "all-scroll", "size_all", "size-all", "all-resize", "move",
            "4498f0e0c1937ffe01fd06f973665830", "9081237383d90e509aa00f00170e968f"
        ]
    },
    "alternate": {
        "primary": "up-arrow",
        "aliases": [
            "up_arrow", "center_ptr", "sb_up_arrow"
        ]
    },
    "link": {
        "primary": "pointer",
        "aliases": [
            "hand", "hand1", "hand2", "pointing_hand",
            "9d800788f1b08800ae810202380a0822", "a2a266d0498c3104214a47bd64ab0fc8",
            "3085a0e285430894940527032f8b26df", "640fb0e74195791501fd1ed57b41487f"
        ]
    },
    "pin": {
        "primary": "pin",
        "aliases": [
            "location-pin", "mark-location"
        ]
    },
    "person": {
        "primary": "person",
        "aliases": [
            "account", "user"
        ]
    }
}


def parse_inf(inf_path):
    """
    Parses Windows Setup Information (.inf) file to extract cursor mappings and theme name.
    """
    schemes = {}
    strings = {}

    current_section = None
    with open(inf_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(";"):
                continue
            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1].strip().lower()
                continue

            if current_section == "strings":
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip().lower()
                    v = v.strip().strip('"').strip("'")
                    strings[k] = v

            elif current_section in ("wreg", "scheme.reg"):
                parts = [p.strip().strip('"') for p in line.split(",")]
                if len(parts) >= 5:
                    reg_key = parts[2].lower()
                    val = parts[4]
                    val_clean = val.replace("%10%\\%cur_dir%\\", "").replace("%10%\\%CUR_DIR%\\", "")
                    val_clean = val_clean.strip("%").lower()
                    schemes[reg_key] = val_clean

    def resolve_str(name):
        n = name.lower()
        if n in strings:
            return strings[n]
        return name

    theme_name = strings.get("scheme_name", os.path.basename(os.path.dirname(inf_path)))

    reg_to_role = {
        "arrow": "pointer",
        "help": "help",
        "appstarting": "working",
        "wait": "busy",
        "crosshair": "precision",
        "precisionhair": "precision",
        "ibeam": "beam",
        "nwpen": "handwriting",
        "no": "unavailable",
        "sizens": "vert",
        "sizewe": "horz",
        "sizenwse": "dgn1",
        "sizenesw": "dgn2",
        "sizeall": "move",
        "uparrow": "alternate",
        "hand": "link",
        "person": "person",
        "pin": "pin"
    }

    file_to_role = {}
    for reg_k, filename_var in schemes.items():
        actual_file = resolve_str(filename_var)
        role = reg_to_role.get(reg_k)
        if role and actual_file:
            file_to_role[actual_file.lower()] = role

    return theme_name, file_to_role


def write_raw_png(width, height, raw_scanlines, out_png_path):
    """
    Writes raw RGBA scanlines (with filter byte 0) to a PNG file using zlib.
    """
    def chunk(tag, data):
        crc = zlib.crc32(tag + data) & 0xffffffff
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    idat = zlib.compress(bytes(raw_scanlines), 9)

    png_bytes = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
    with open(out_png_path, "wb") as f:
        f.write(png_bytes)


def cur_to_png(cur_data, out_png_path):
    """
    Extracts image data from a single .cur file and writes to out_png_path.
    Directly extracts full 32-bit ARGB with 8-bit alpha channel to preserve
    clean anti-aliasing and prevent 1-bit thresholding black halo artifacts.
    """
    magic, type_, count = struct.unpack("<HHH", cur_data[:6])
    assert type_ == 2, f"Expected cursor type 2, got {type_}"

    w, h, col, rsv, xh, yh, sz, off = struct.unpack("<BBBBHHII", cur_data[6:22])
    actual_width = 256 if w == 0 else w
    actual_height = 256 if h == 0 else h

    payload = cur_data[off : off + sz]

    # Embedded PNG check
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        with open(out_png_path, "wb") as f:
            f.write(payload)
        return (actual_width, actual_height, xh, yh)

    # DIB Header
    header_size = struct.unpack("<I", payload[:4])[0]
    if header_size >= 40:
        biWidth, biHeight, biPlanes, biBitCount = struct.unpack("<IIHH", payload[4:16])
        real_h = biHeight // 2
        real_w = biWidth

        if biBitCount == 32:
            xor_data = payload[header_size : header_size + real_w * real_h * 4]
            # Verify if 8-bit alpha is present
            has_alpha = any(xor_data[i + 3] > 0 for i in range(0, len(xor_data), 4))
            if has_alpha:
                # Bottom-up BGRA -> Top-down RGBA PNG scanlines
                raw_scanlines = bytearray()
                for y in range(real_h - 1, -1, -1):
                    raw_scanlines.append(0)  # Filter type None
                    row_start = y * real_w * 4
                    row = xor_data[row_start : row_start + real_w * 4]
                    for x in range(real_w):
                        b = row[x * 4]
                        g = row[x * 4 + 1]
                        r = row[x * 4 + 2]
                        a = row[x * 4 + 3]
                        raw_scanlines.extend((r, g, b, a))

                write_raw_png(real_w, real_h, raw_scanlines, out_png_path)
                return (real_w, real_h, xh, yh)

    # Fallback to ImageMagick convert for 1bpp / 4bpp / 8bpp legacy cursors
    with tempfile.NamedTemporaryFile(suffix=".cur", delete=False) as tf:
        tf.write(cur_data)
        tf_name = tf.name
    try:
        cmd = ["convert", f"{tf_name}[0]", out_png_path]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            raise RuntimeError(f"convert failed: {res.stderr.decode()}")
    finally:
        if os.path.exists(tf_name):
            os.remove(tf_name)

    return (actual_width, actual_height, xh, yh)


def parse_ani(ani_path):
    """
    Parses a Windows animated cursor (.ani) RIFF file.
    Returns list of (cur_bytes, delay_ms)
    """
    with open(ani_path, "rb") as f:
        d = f.read()

    if not (d[:4] == b"RIFF" and d[8:12] == b"ACON"):
        raise ValueError(f"File {ani_path} is not a valid RIFF ACON file")

    pos = 12
    anih_data = None
    rate_data = None
    seq_data = None
    frames = []

    while pos < len(d):
        cid = d[pos : pos + 4]
        sz = struct.unpack("<I", d[pos + 4 : pos + 8])[0]
        payload = d[pos + 8 : pos + 8 + sz]
        if cid == b"anih":
            anih_data = payload
        elif cid == b"rate":
            rate_data = payload
        elif cid == b"seq ":
            seq_data = payload
        elif cid == b"LIST" and payload[:4] == b"fram":
            fram_pos = 4
            while fram_pos < len(payload):
                sub_id = payload[fram_pos : fram_pos + 4]
                sub_sz = struct.unpack("<I", payload[fram_pos + 4 : fram_pos + 8])[0]
                sub_data = payload[fram_pos + 8 : fram_pos + 8 + sub_sz]
                if sub_id == b"icon":
                    frames.append(sub_data)
                fram_pos += 8 + sub_sz + (sub_sz % 2)
        pos += 8 + sz + (sz % 2)

    if not anih_data:
        raise ValueError("Missing 'anih' header in ANI file")

    cbSize, nFrames, nSteps, cx, cy, cBitCount, nPlanes, jifRate, flags = struct.unpack(
        "<IIIIIIIII", anih_data[:36]
    )

    default_delay_ms = max(int(jifRate * (1000 / 60)), 16)

    rates = []
    if rate_data:
        count = len(rate_data) // 4
        rates = [max(int(r * (1000 / 60)), 16) for r in struct.unpack(f"<{count}I", rate_data)]

    seq = list(range(nFrames))
    if seq_data:
        count = len(seq_data) // 4
        seq = list(struct.unpack(f"<{count}I", seq_data))

    frame_items = []
    for step_idx, frame_idx in enumerate(seq):
        cur_bytes = frames[frame_idx]
        delay = rates[step_idx] if step_idx < len(rates) else default_delay_ms
        frame_items.append((cur_bytes, delay))

    return frame_items


def generate_multisize_pngs(base_png, orig_w, orig_h, orig_xh, orig_yh, target_sizes, tmp_dir, prefix):
    """
    Generates scaled PNGs and calculates hotspot coordinates for multiple cursor sizes.
    Uses high-quality Lanczos resampling.
    """
    scale_factor = 1.35  # Compensate for Windows 32px canvas padding relative to Linux native sizes
    results = []
    
    for size in target_sizes:
        target_canvas = int(round(size * scale_factor))
        # Ensure hotspot scales proportionally
        scaled_xh = int(round(orig_xh * (target_canvas / orig_w)))
        scaled_yh = int(round(orig_yh * (target_canvas / orig_h)))

        out_png = os.path.join(tmp_dir, f"{prefix}_{size}.png")
        subprocess.run([
            "convert", base_png,
            "-filter", "Lanczos",
            "-resize", f"{target_canvas}x{target_canvas}",
            out_png
        ], check=True)

        results.append((size, scaled_xh, scaled_yh, out_png))

    return results


def build_xcursor_from_cur(cur_path, output_xcursor_path, tmp_dir, target_sizes):
    """
    Converts a single .cur file into an X11 cursor with multiple nominal sizes.
    """
    with open(cur_path, "rb") as f:
        data = f.read()

    base_name = os.path.basename(cur_path)
    base_png = os.path.join(tmp_dir, f"{base_name}_base.png")
    w, h, xhot, yhot = cur_to_png(data, base_png)

    scaled_items = generate_multisize_pngs(base_png, w, h, xhot, yhot, target_sizes, tmp_dir, base_name)

    cfg_lines = []
    for nominal_size, s_xh, s_yh, png_p in scaled_items:
        cfg_lines.append(f"{nominal_size} {s_xh} {s_yh} {png_p}\n")

    cfg_path = os.path.join(tmp_dir, f"{base_name}.cfg")
    with open(cfg_path, "w", encoding="utf-8") as f:
        f.writelines(cfg_lines)

    cmd = ["xcursorgen", cfg_path, output_xcursor_path]
    subprocess.run(cmd, check=True)


def build_xcursor_from_ani(ani_path, output_xcursor_path, tmp_dir, target_sizes):
    """
    Converts a Windows .ani into a multi-size animated X11 cursor.
    """
    frame_items = parse_ani(ani_path)
    base_name = os.path.basename(ani_path)

    cfg_lines = []
    for f_idx, (frame_bytes, delay_ms) in enumerate(frame_items):
        frame_base_png = os.path.join(tmp_dir, f"{base_name}_f{f_idx:02d}_base.png")
        w, h, xhot, yhot = cur_to_png(frame_bytes, frame_base_png)
        scaled_items = generate_multisize_pngs(
            frame_base_png, w, h, xhot, yhot, target_sizes, tmp_dir, f"{base_name}_f{f_idx:02d}"
        )
        for nominal_size, s_xh, s_yh, png_p in scaled_items:
            cfg_lines.append(f"{nominal_size} {s_xh} {s_yh} {png_p} {delay_ms}\n")

    cfg_path = os.path.join(tmp_dir, f"{base_name}.cfg")
    with open(cfg_path, "w", encoding="utf-8") as f:
        f.writelines(cfg_lines)

    cmd = ["xcursorgen", cfg_path, output_xcursor_path]
    subprocess.run(cmd, check=True)


def convert_theme(input_dir, output_theme_dir, custom_theme_name=None, comment=None, target_sizes=None):
    """
    Converts a directory containing Windows cursors into a standard X11 cursor theme.
    """
    if target_sizes is None:
        target_sizes = [24, 28, 32, 40, 48, 64]

    input_path = Path(input_dir).resolve()
    if not input_path.is_dir():
        raise NotADirectoryError(f"Directory not found: {input_dir}")

    inf_files = list(input_path.glob("*.inf")) + list(input_path.glob("*.INF"))
    inf_theme_name = None
    file_to_role = {}
    if inf_files:
        inf_theme_name, file_to_role = parse_inf(str(inf_files[0]))

    theme_name = custom_theme_name or inf_theme_name or input_path.name

    cursors_dir = os.path.join(output_theme_dir, "cursors")
    os.makedirs(cursors_dir, exist_ok=True)

    index_theme_path = os.path.join(output_theme_dir, "index.theme")
    with open(index_theme_path, "w", encoding="utf-8") as f:
        f.write("[Icon Theme]\n")
        f.write(f"Name={theme_name}\n")
        f.write(f"Comment={comment or theme_name}\n")
        f.write("Inherits=\"hicolor\"\n")

    cursor_theme_path = os.path.join(output_theme_dir, "cursor.theme")
    with open(cursor_theme_path, "w", encoding="utf-8") as f:
        f.write("[Icon Theme]\n")
        f.write(f"Inherits={theme_name}\n")

    cursor_files = list(input_path.glob("*.cur")) + list(input_path.glob("*.CUR")) + \
                   list(input_path.glob("*.ani")) + list(input_path.glob("*.ANI"))

    print(f"[*] Processing theme '{theme_name}' with {len(cursor_files)} cursor files...")

    name_fallback_map = {
        "pointer": "pointer",
        "arrow": "pointer",
        "help": "help",
        "working": "working",
        "busy": "busy",
        "wait": "busy",
        "precision": "precision",
        "crosshair": "precision",
        "cross": "precision",
        "beam": "beam",
        "text": "beam",
        "ibeam": "beam",
        "handwriting": "handwriting",
        "hand": "link",
        "link": "link",
        "unavailable": "unavailable",
        "no": "unavailable",
        "vert": "vert",
        "horz": "horz",
        "dgn1": "dgn1",
        "dgn2": "dgn2",
        "move": "move",
        "alternate": "alternate",
        "pin": "pin",
        "person": "person"
    }

    with tempfile.TemporaryDirectory() as tmp_dir:
        created_primaries = {}

        for cur_file in cursor_files:
            fname = cur_file.name.lower()
            role = file_to_role.get(fname)
            if not role:
                stem = cur_file.stem.lower()
                role = name_fallback_map.get(stem)

            if not role:
                print(f"[-] Unrecognized cursor role for: {cur_file.name}, skipping.")
                continue

            role_info = CURSOR_ROLE_MAPPING.get(role)
            if not role_info:
                print(f"[-] No target mapping defined for role '{role}' ({cur_file.name})")
                continue

            primary_name = role_info["primary"]
            primary_path = os.path.join(cursors_dir, primary_name)

            if cur_file.suffix.lower() == ".ani":
                build_xcursor_from_ani(str(cur_file), primary_path, tmp_dir, target_sizes)
            else:
                build_xcursor_from_cur(str(cur_file), primary_path, tmp_dir, target_sizes)

            created_primaries[role] = primary_name
            print(f"  [+] Created primary cursor: {primary_name} (from {cur_file.name})")

            for alias in role_info["aliases"]:
                alias_path = os.path.join(cursors_dir, alias)
                if os.path.lexists(alias_path):
                    os.remove(alias_path)
                os.symlink(primary_name, alias_path)

        if "pointer" in created_primaries:
            for extra in ["default", "arrow", "top_left_arrow"]:
                p = os.path.join(cursors_dir, extra)
                if not os.path.lexists(p):
                    os.symlink(created_primaries["pointer"], p)

    print(f"[✓] Successfully built cursor theme '{theme_name}' at: {output_theme_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert Windows custom cursor sets (.cur / .ani) to Linux / GNOME cursor themes."
    )
    parser.add_argument(
        "input",
        help="Input directory containing .cur / .ani / .inf files (or directory of themes like wincur)"
    )
    parser.add_argument(
        "-o", "--output",
        default=os.path.expanduser("~/.icons"),
        help="Output base directory (default: ~/.icons)"
    )
    parser.add_argument(
        "-n", "--name",
        help="Override theme name (only used if converting a single theme folder)"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Automatically apply the converted theme in GNOME using gsettings"
    )
    parser.add_argument(
        "--sizes",
        default="24,28,32,40,48,64",
        help="Comma-separated list of nominal cursor sizes to generate (default: 24,28,32,40,48,64)"
    )

    args = parser.parse_args()

    if not shutil.which("xcursorgen"):
        sys.exit("Error: 'xcursorgen' is not installed. Install it via: sudo apt install x11-apps (or xcursorgen)")
    if not shutil.which("convert"):
        sys.exit("Error: 'convert' (ImageMagick) is not installed. Install it via: sudo apt install imagemagick")

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        sys.exit(f"Error: Path {input_path} does not exist.")

    sizes = [int(s.strip()) for s in args.sizes.split(",") if s.strip().isdigit()]

    direct_cursors = list(input_path.glob("*.cur")) + list(input_path.glob("*.ani"))

    themes_to_convert = []
    if direct_cursors:
        themes_to_convert.append((input_path, args.name))
    else:
        subdirs = [p for p in input_path.iterdir() if p.is_dir()]
        for s in subdirs:
            if list(s.glob("*.cur")) or list(s.glob("*.ani")):
                themes_to_convert.append((s, None))

    if not themes_to_convert:
        sys.exit(f"Error: No .cur or .ani cursors found in {input_path} or its direct subdirectories.")

    converted_theme_names = []
    for sdir, custom_name in themes_to_convert:
        theme_dir_name = custom_name or sdir.name
        out_theme_dir = os.path.join(args.output, theme_dir_name)
        convert_theme(sdir, out_theme_dir, custom_theme_name=custom_name, target_sizes=sizes)
        converted_theme_names.append(theme_dir_name)

    print("\nAll conversions finished!")
    print(f"Themes installed in: {args.output}")

    if args.apply and converted_theme_names:
        chosen_theme = converted_theme_names[0]
        print(f"Applying GNOME cursor theme: {chosen_theme}...")
        subprocess.run(["gsettings", "set", "org.gnome.desktop.interface", "cursor-theme", chosen_theme])
        print("[✓] GNOME cursor theme updated.")


if __name__ == "__main__":
    main()
