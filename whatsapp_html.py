"""Convierte una exportación ZIP de WhatsApp en un HTML autónomo y privado."""

import argparse
import base64
from dataclasses import dataclass
from html import escape
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import stat
import sys
import tempfile
import unicodedata
import zipfile


MAX_BYTES = 2 * 1024**3
MAX_FILES = 50_000
INVISIBLE = str.maketrans("", "", "\ufeff\u200e\u200f\u202a\u202b\u202c\u2066\u2067\u2068\u2069")
HEADER = re.compile(
    r"^\[?(?P<date>\d{1,4}[/.\-]\d{1,2}[/.\-]\d{1,4}),?\s+"
    r"(?P<time>\d{1,2}:\d{2}(?::\d{2})?(?:\s*[ap]\.?\s*m\.?)?)"
    r"(?:\]\s*|\s+[-–]\s+)(?P<body>.*)$", re.IGNORECASE
)
ATTACHED = re.compile(r"<(?:(?:attached|adjunto|archivo adjunto):)\s*([^>]+)>", re.I)
ANDROID_ATTACHED = re.compile(r"^(.+?)\s+\((?:archivo adjunto|file attached)\)", re.M | re.I)
MEDIA_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".webp": "image/webp", ".avif": "image/avif",
    ".opus": "audio/ogg", ".ogg": "audio/ogg", ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4", ".aac": "audio/aac", ".wav": "audio/wav",
    ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
    ".3gp": "video/3gpp",
}


@dataclass
class Message:
    date: str
    time: str
    sender: str | None
    text: str


@dataclass
class Asset:
    name: str
    path: Path
    key: str


def clean(text):
    return unicodedata.normalize("NFC", text.translate(INVISIBLE))


def parse_chat(text):
    # shortcut: una cabecera pegada dentro del texto es ambigua; usar datos estructurados si se necesita fidelidad forense.
    messages = []
    for line in text.splitlines():
        # Solo se limpian marcas de dirección; se conserva la indentación del mensaje.
        line = line.translate(INVISIBLE)
        match = HEADER.match(line)
        if match:
            body = match["body"]
            sender, separator, content = body.partition(": ")
            messages.append(Message(match["date"], match["time"],
                                    sender if separator else None,
                                    content if separator else body))
        elif messages:
            messages[-1].text += "\n" + line
        elif line.strip():
            messages.append(Message("", "", None, line))
    return messages


def extract_zip(source, destination, advance=lambda: None):
    files = {}
    with zipfile.ZipFile(source) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_FILES or sum(e.file_size for e in entries) > MAX_BYTES:
            raise ValueError("ZIP demasiado grande: límite de 2 GiB descomprimidos y 50.000 entradas.")
        total = 0
        for index, entry in enumerate(entries):
            name = clean(entry.filename.replace("\\", "/"))
            parts = PurePosixPath(name).parts
            if (not parts or name.startswith("/") or ".." in parts
                    or any(":" in part for part in parts)
                    or stat.S_ISLNK(entry.external_attr >> 16)):
                raise ValueError("El ZIP contiene una ruta no segura o un enlace simbólico.")
            if entry.is_dir():
                continue
            if name in files:
                raise ValueError("El ZIP contiene nombres de archivo duplicados.")
            # Nombres internos numéricos: ninguna ruta del ZIP llega al sistema de archivos.
            target = destination / str(index)
            with archive.open(entry) as incoming, target.open("xb") as outgoing:
                while chunk := incoming.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise ValueError("Se ha superado el límite descomprimido de 2 GiB.")
                    outgoing.write(chunk)
            files[name] = target
            advance()
    return files


def read_chat(path):
    data = path.read_bytes()
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    return data.decode("utf-8-sig")


def select_chat(files, requested=None):
    candidates = [name for name in files if name.lower().endswith(".txt")
                  and not name.startswith("__MACOSX/")]
    if requested:
        requested = clean(requested.replace("\\", "/"))
        if requested not in candidates:
            raise ValueError("El TXT indicado con --chat no existe dentro del ZIP.")
        candidates = [requested]
    matches = []
    for name in candidates:
        try:
            text = read_chat(files[name])
        except UnicodeError:
            continue
        if any(HEADER.match(line.translate(INVISIBLE)) for line in text.splitlines()):
            matches.append((name, text))
    if not matches:
        raise ValueError("No se ha encontrado un TXT de exportación Android/iPhone válido (UTF-8 o UTF-16).")
    if len(matches) > 1:
        raise ValueError("Hay varias conversaciones. Selecciona su ruta con --chat: "
                         + ", ".join(name for name, _ in matches))
    return matches[0]


def index_assets(assets):
    by_name, by_basename = {}, {}
    for asset in assets:
        by_name[asset.name] = [asset]
        by_basename.setdefault(PurePosixPath(asset.name).name, []).append(asset)
    return by_name, by_basename


def find_assets(text, assets, chat_name, lookup=None):
    by_name, by_basename = lookup if lookup is not None else index_assets(assets)
    normalized = clean(text)
    references = [m[1].strip() for m in ATTACHED.finditer(normalized)]
    references += [m[1].strip() for m in ANDROID_ATTACHED.finditer(normalized)]
    found, missing = [], []
    parent = PurePosixPath(chat_name).parent
    for reference in references:
        local_name = str(parent / reference)
        candidates = by_name.get(local_name) or by_basename.get(reference, [])
        if len(candidates) == 1:
            if candidates[0] not in found:
                found.append(candidates[0])
        else:
            missing.append(reference)
    return found, missing


def write_base64(output, path):
    with path.open("rb") as source:
        # Múltiplo de tres para concatenar base64 sin padding intermedio.
        while chunk := source.read(3 * 64 * 1024):
            output.write(base64.b64encode(chunk).decode("ascii"))


def write_asset(output, asset):
    name = escape(PurePosixPath(asset.name).name)
    mime = MEDIA_TYPES.get(PurePosixPath(asset.name).suffix.lower())
    output.write(f'<template id="{asset.key}"><figure>')
    if mime:
        kind = mime.split("/")[0]
        attributes = f'alt="{name}" loading="lazy"' if kind == "image" else 'controls preload="none"'
        tag = "img" if kind == "image" else kind
        output.write(f'<{tag} {attributes} src="data:{mime};base64,')
        write_base64(output, asset.path)
        output.write('">' if tag == "img" else f'"></{tag}>')
        output.write(f'<figcaption><a download="{name}">{name} · Descargar</a></figcaption>')
    else:
        output.write(f'<figcaption><a download="{name}" href="data:application/octet-stream;base64,')
        write_base64(output, asset.path)
        output.write(f'">📎 {name} · Descargar</a></figcaption>')
    output.write('</figure></template>\n')


def render(output, messages, assets, chat_name, title, me, advance=lambda: None):
    template = Path(__file__).with_name("viewer.html").read_text(encoding="utf-8")
    header, footer = template.split("<!-- MESSAGES -->")
    nonce = secrets.token_hex(16)
    participants = {m.sender for m in messages if m.sender is not None}
    header = (header.replace("{{TITLE}}", escape(title))
              .replace("{{SUMMARY}}", f"{len(messages):,} mensajes · {len(participants)} participantes · {len(assets)} adjuntos")
              .replace("{{NONCE}}", nonce))
    output.write(header)
    used = set()
    missing_count = 0
    previous_date = None
    lookup = index_assets(assets)
    own_name = clean(me) if me is not None else None
    for message in messages:
        if message.date and message.date != previous_date:
            output.write(f'<div class="day">{escape(message.date)}</div>\n')
            previous_date = message.date
        own = own_name is not None and clean(message.sender or "") == own_name
        style = "system" if message.sender is None else "outgoing" if own else "incoming"
        output.write(f'<article class="message {style}">')
        if message.sender is not None:
            output.write(f'<strong class="sender">{escape(message.sender)}</strong>')
        output.write(f'<div class="text">{escape(message.text)}</div>')
        attached, missing = find_assets(message.text, assets, chat_name, lookup)
        missing_count += len(missing)
        for asset in attached:
            output.write(f'<div class="attachment" data-file="{asset.key}"></div>')
            used.add(asset.key)
        if missing:
            output.write('<small class="missing">Adjunto ausente o ambiguo en el ZIP</small>')
        output.write(f'<time>{escape(message.time)}</time></article>\n')
        advance()
    unused = [asset for asset in assets if asset.key not in used]
    if unused:
        output.write('<section class="extras"><h2>Otros archivos del ZIP</h2>'
                     '<p>Sin referencia identificable en los mensajes; se conservan aquí.</p>')
        for asset in unused:
            output.write(f'<div class="attachment" data-file="{asset.key}"></div>')
        output.write('</section>')
    output.write('</main>\n')
    for asset in assets:
        write_asset(output, asset)
        advance()
    output.write(footer.replace("{{NONCE}}", nonce))
    return missing_count


def convert(source, output, me=None, chat=None, advance=lambda: None):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_file() or not zipfile.is_zipfile(source):
        raise ValueError("La entrada debe ser una exportación .zip válida de WhatsApp.")
    if output.suffix.lower() != ".html":
        raise ValueError("La salida debe tener extensión .html.")
    if output.exists():
        raise ValueError("La salida ya existe. Elige otra ruta para no sobrescribirla.")
    if not output.parent.is_dir():
        raise ValueError("La carpeta de salida no existe.")
    with tempfile.TemporaryDirectory(prefix="whatsapp-html-") as directory:
        files = extract_zip(source, Path(directory), advance)
        chat_name, text = select_chat(files, chat)
        messages = parse_chat(text)
        if me is not None and clean(me) not in {clean(m.sender) for m in messages if m.sender is not None}:
            raise ValueError("El nombre de --me no coincide con ningún remitente del TXT.")
        assets = [Asset(name, path, f"file-{index}") for index, (name, path) in enumerate(files.items())
                  if name != chat_name and not name.startswith("__MACOSX/")
                  and PurePosixPath(name).name != ".DS_Store"]
        title = PurePosixPath(chat_name).stem
        if title == "_chat":
            title = source.stem
        temporary_output = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                             dir=output.parent, prefix=".whatsapp-", suffix=".tmp",
                                             delete=False) as stream:
                temporary_output = Path(stream.name)
                missing = render(stream, messages, assets, chat_name, title, me, advance)
            # Publicación atómica sin reemplazar un archivo creado mientras se convertía.
            os.link(temporary_output, output)
        finally:
            if temporary_output is not None:
                temporary_output.unlink(missing_ok=True)
    return len(messages), len(assets), missing


def main(argv=None):
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, epilog="Local y sin conexión. El ZIP original nunca se modifica.")
    parser.add_argument("zip", type=Path, help="ZIP creado con Exportar chat → Incluir archivos")
    parser.add_argument("-o", "--output", type=Path, help="HTML de salida (por defecto, junto al ZIP)")
    parser.add_argument("--me", help="Tu nombre exacto en el TXT: coloca tus mensajes a la derecha")
    parser.add_argument("--chat", help="Ruta del TXT dentro del ZIP, si contiene varias conversaciones")
    parser.add_argument("--no-color", action="store_true", help="Desactiva los colores de la terminal")
    args = parser.parse_args(argv)
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
    except ImportError:
        parser.exit(1, "Instala la dependencia: python -m pip install -r requirements.txt\n")
    console = Console(no_color=args.no_color or "NO_COLOR" in os.environ, highlight=False)
    console.print(Panel("[bold white]WhatsApp → HTML[/bold white]\n[dim]Tu conversación, en un solo archivo. Sin subir nada.[/dim]",
                        border_style="green", padding=(1, 2)))
    output = args.output or args.zip.with_suffix(".html")
    try:
        with Progress(SpinnerColumn("dots", style="green"), TextColumn("{task.description}"),
                      TimeElapsedColumn(), console=console, transient=True,
                      disable=not console.is_terminal) as progress:
            task = progress.add_task("Extrayendo, leyendo e incorporando archivos…", total=None)
            counts = convert(args.zip, output, args.me, args.chat,
                             lambda: progress.advance(task))
        console.print("[bold green]✓ HTML creado. Carpeta temporal eliminada.[/bold green]")
        console.print(str(output.resolve()), markup=False)
        console.print(f"[dim]{counts[0]:,} mensajes · {counts[1]} adjuntos · {output.stat().st_size / 1024**2:.1f} MiB[/dim]")
        if counts[2]:
            console.print(f"[yellow]Aviso: {counts[2]} referencias a adjuntos ausentes o ambiguos; se conserva su texto.[/yellow]")
        console.print("[dim]El HTML contiene datos privados sin cifrar. Compártelo con cuidado.[/dim]")
        return 0
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelado. Se han limpiado los archivos temporales.[/yellow]")
        return 130
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, NotImplementedError, EOFError) as error:
        console.print("Error: " + str(error), style="red", markup=False)
        return 1


if __name__ == "__main__":
    sys.exit(main())
