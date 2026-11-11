#!/usr/bin/env python3
"""
arte_do_dia.py — Envia por e-mail a "Obra de arte do dia" do Google Arts & Culture,
com a imagem em anexo e os dados da obra/artista no corpo da mensagem.

Dependências:
    pip install requests beautifulsoup4
    # opcional (fallback, caso a home não traga o link no HTML estático):
    pip install playwright && playwright install chromium

Configuração (variáveis de ambiente, ou um arquivo .env ao lado do script):
    SMTP_HOST   (padrão: smtp.gmail.com)
    SMTP_PORT   (padrão: 587, STARTTLS)
    SMTP_USER   usuário SMTP (ex.: seu Gmail)
    SMTP_PASS   senha de app (Gmail: https://myaccount.google.com/apppasswords)
    MAIL_FROM   (padrão: SMTP_USER)
    MAIL_TO     um ou mais destinatários separados por vírgula

Uso:
    python3 arte_do_dia.py                 # busca a obra do dia e envia
    python3 arte_do_dia.py --dry-run       # não envia; salva prévia em ./preview/
    python3 arte_do_dia.py --force         # envia mesmo que já tenha enviado hoje
    python3 arte_do_dia.py --url <URL>     # usa uma página /asset/... específica (teste)
    python3 arte_do_dia.py --debug-home    # salva o HTML da home e mostra a obra detectada

Agendamento diário (cron, todo dia às 08:00):
    0 8 * * * /usr/bin/python3 /caminho/arte_do_dia.py >> /caminho/arte_do_dia.log 2>&1
"""

import argparse
import html
import json
import mimetypes
import os
import re
import smtplib
import sys
from datetime import date
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://artsandculture.google.com"
HOME_URL = f"{BASE}/?hl=pt-BR"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.5",
}
STATE_FILE = Path(__file__).with_name(".arte_do_dia_state.json")
IMAGE_SIZE = "s2048"  # lado maior em px (googleusercontent: =s2048)

# Campos pedidos, na ordem de exibição, com apelidos (pt-BR e en) para casar
# com os rótulos que a página usa. Rótulos são comparados normalizados.
FIELDS = [
    ("Título", ["título", "title"]),
    ("Criador", ["criador", "creator"]),
    ("Vida do criador", ["vida do criador", "creator lifespan", "lifespan"]),
    ("Nacionalidade do criador", ["nacionalidade do criador", "creator nationality"]),
    ("Sexo do criador", ["sexo do criador", "gênero do criador", "creator gender"]),
    ("Local de nascimento do criador",
     ["local de nascimento do criador", "creator birth place"]),
    ("Local da morte do criador",
     ["local da morte do criador", "creator death place"]),
    ("Dimensões físicas", ["dimensões físicas", "physical dimensions"]),
    ("Etiquetas", ["etiquetas", "tags"]),
    ("Proveniência", ["proveniência", "provenance"]),
    ("Informações sobre o artista", ["informações sobre o artista", "artist information"]),
    ("Pintor", ["pintor", "painter"]),
    ("Tipo", ["tipo", "type"]),
    ("Link externo", ["link externo", "external link"]),
]


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().rstrip(":").strip().casefold()


def get(url: str) -> requests.Response:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r


def with_hl(url: str) -> str:
    """Garante hl=pt-BR para os rótulos virem em português."""
    if "hl=" in url:
        return url
    return url + ("&" if "?" in url else "?") + "hl=pt-BR"


# --------------------------------------------------------------------------- #
# 1) Descobrir a página da "Obra de arte do dia"
# --------------------------------------------------------------------------- #
MARKER_RE = re.compile(r"^\s*(obra de arte do dia|artwork of the day)\s*$", re.I)
ASSET_HREF_RE = re.compile(r"/asset/")

# Executado no navegador: acha o título do bloco e devolve o primeiro link
# /asset/... que vem DEPOIS dele no documento.
JS_FIND = r"""
() => {
  const re = /^\s*(obra de arte do dia|artwork of the day)\s*$/i;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const links = [...document.querySelectorAll('a[href*="/asset/"]')];
  let n;
  while ((n = walker.nextNode())) {
    if (!re.test(n.nodeValue)) continue;
    const el = n.parentElement;
    const hit = links.find(
      a => el.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_FOLLOWING
    );
    if (hit) return hit.href;
  }
  return null;
}
"""


def find_asset_in_html(page_html: str) -> str | None:
    """Acha o link da obra do dia no HTML estático, olhando só o conteúdo visível.

    Ignora <script>/<style>: lá o texto 'Obra de arte do dia' aparece em strings de
    tradução, e o primeiro /asset/ depois delas é outra obra qualquer.
    """
    soup = BeautifulSoup(page_html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    heading = soup.find(string=MARKER_RE)
    if not heading:
        return None
    link = heading.find_next("a", href=ASSET_HREF_RE)
    return urljoin(BASE, link["href"]) if link else None


def render_home() -> tuple[str, str | None] | None:
    """Renderiza a home com Chromium (Playwright). Devolve (html, url_da_obra) ou None."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(locale="pt-BR", user_agent=HEADERS["User-Agent"])
        page.goto(HOME_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2500)  # dá tempo de o bloco ser desenhado
        url = page.evaluate(JS_FIND)
        content = page.content()
        browser.close()
    return content, url


def discover_asset_url() -> str:
    # Permite forçar manualmente (útil se a home mudar de estrutura)
    forced = os.environ.get("ASSET_URL")
    if forced:
        return forced

    url = find_asset_in_html(get(HOME_URL).text)
    if url:
        print("Descoberta: HTML estático")
        return url

    rendered = render_home()
    if rendered and rendered[1]:
        print("Descoberta: página renderizada (Playwright)")
        return rendered[1]

    hint = (
        "" if rendered is not None
        else " O Playwright não está instalado (pip install playwright && "
             "playwright install chromium); a home costuma exigir renderização."
    )
    raise RuntimeError(
        "Não consegui localizar a 'Obra de arte do dia' na página inicial." + hint
        + " Use --debug-home para inspecionar ou --url <página /asset/...>."
    )


def debug_home() -> int:
    """Salva o HTML estático e o renderizado em ./preview/ e mostra o que foi achado."""
    out = Path(__file__).with_name("preview")
    out.mkdir(exist_ok=True)
    static_html = get(HOME_URL).text
    (out / "home_static.html").write_text(static_html, encoding="utf-8")
    print("Estático  :", find_asset_in_html(static_html))
    rendered = render_home()
    if rendered is None:
        print("Renderizado: Playwright não instalado")
    else:
        (out / "home_rendered.html").write_text(rendered[0], encoding="utf-8")
        print("Renderizado:", rendered[1])
    print(f"HTML salvo em {out}/ (home_static.html / home_rendered.html)")
    return 0


# --------------------------------------------------------------------------- #
# 2) Extrair metadados e imagem da página da obra
# --------------------------------------------------------------------------- #
def parse_details(soup: BeautifulSoup) -> dict[str, str]:
    """Lê os pares 'Rótulo: valor' da lista de detalhes da obra."""
    found: dict[str, str] = {}
    for li in soup.find_all("li"):
        text = li.get_text(" ", strip=True)
        if ":" not in text:
            continue
        label, _, value = text.partition(":")
        label_n = norm(label)
        if not label_n or len(label_n) > 60 or not value.strip():
            continue

        anchors = [a for a in li.find_all("a") if a.get_text(strip=True)]
        if label_n in ("etiquetas", "tags") and anchors:
            value = ", ".join(dict.fromkeys(a.get_text(strip=True) for a in anchors))
        elif label_n in ("link externo", "external link"):
            href = next((a.get("href") for a in li.find_all("a") if a.get("href")), "")
            value = urljoin(BASE, href) if href else value.strip()
        found.setdefault(label_n, value.strip())
    return found


def meta(soup: BeautifulSoup, prop: str) -> str:
    tag = soup.find("meta", attrs={"property": prop}) or soup.find(
        "meta", attrs={"name": prop}
    )
    return (tag.get("content") or "").strip() if tag else ""


def fetch_artwork(asset_url: str) -> dict:
    asset_url = with_hl(asset_url)
    soup = BeautifulSoup(get(asset_url).text, "html.parser")
    details = parse_details(soup)

    # Fallbacks de título/criador via og:title ("Título - Criador - Google Arts & Culture")
    og_title = re.sub(r"\s*-\s*Google Arts (&|&amp;) Culture\s*$", "", meta(soup, "og:title"))
    parts = [p.strip() for p in og_title.split(" - ")]
    if parts and parts[0]:
        details.setdefault("título", parts[0])
    if len(parts) > 1:
        details.setdefault("criador", parts[1])

    image = meta(soup, "og:image")
    if not image:
        raise RuntimeError("Imagem (og:image) não encontrada na página da obra.")
    image_hq = re.sub(r"=[wsh]\d.*$", "", image) + f"={IMAGE_SIZE}"

    rows = []
    for label, aliases in FIELDS:
        value = next((details[a] for a in aliases if a in details), "")
        rows.append((label, value or "—"))

    return {
        "url": asset_url,
        "asset_id": asset_url.split("?")[0].rstrip("/").split("/")[-1],
        "image_url": image_hq,
        "rows": rows,
    }


def download_image(url: str) -> tuple[bytes, str, str]:
    r = get(url)
    ctype = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
    ext = mimetypes.guess_extension(ctype) or ".jpg"
    if ext == ".jpe":
        ext = ".jpg"
    return r.content, ctype, ext


# --------------------------------------------------------------------------- #
# 3) Montar e enviar o e-mail
# --------------------------------------------------------------------------- #
def slugify(s: str) -> str:
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE).strip().lower()
    return re.sub(r"[\s_-]+", "-", s)[:60] or "obra"


def build_message(art: dict, img: bytes, ctype: str, ext: str) -> EmailMessage:
    title = dict(art["rows"]).get("Título", "Obra de arte do dia")
    sender = os.environ.get("MAIL_FROM") or os.environ["SMTP_USER"]
    recipients = [r.strip() for r in os.environ["MAIL_TO"].split(",") if r.strip()]

    msg = EmailMessage()
    msg["Subject"] = f"🎨 Obra de arte do dia ({date.today():%d/%m/%Y}): {title}"
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)

    # Texto simples
    lines = [f"Obra de arte do dia — {date.today():%d/%m/%Y}", ""]
    lines += [f"{label}: {value}" for label, value in art["rows"]]
    lines += ["", f"Página no Google Arts & Culture: {art['url']}"]
    msg.set_content("\n".join(lines))

    # HTML
    trs = []
    for label, value in art["rows"]:
        v = html.escape(value)
        if label == "Link externo" and value.startswith("http"):
            v = f'<a href="{html.escape(value)}">{v}</a>'
        trs.append(
            f'<tr><td style="padding:6px 12px 6px 0;vertical-align:top;'
            f'font-weight:bold;white-space:nowrap">{html.escape(label)}:</td>'
            f'<td style="padding:6px 0">{v}</td></tr>'
        )
    msg.add_alternative(
        f"""<html><body style="font-family:Arial,Helvetica,sans-serif;color:#222">
<h2 style="margin-bottom:4px">🎨 Obra de arte do dia</h2>
<p style="margin-top:0;color:#666">{date.today():%d/%m/%Y} — imagem em anexo</p>
<table style="border-collapse:collapse;font-size:14px">{''.join(trs)}</table>
<p><a href="{html.escape(art['url'])}">Ver no Google Arts &amp; Culture</a></p>
</body></html>""",
        subtype="html",
    )

    maintype, subtype = ctype.split("/", 1)
    msg.add_attachment(
        img, maintype=maintype, subtype=subtype, filename=f"{slugify(title)}{ext}"
    )
    return msg


def send(msg: EmailMessage) -> None:
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=60) as s:
        s.starttls()
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        s.send_message(msg)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="não envia; salva prévia em ./preview/")
    ap.add_argument("--force", action="store_true", help="envia mesmo se já enviou hoje")
    ap.add_argument("--url", help="URL de uma página /asset/... (ignora a descoberta automática)")
    ap.add_argument("--debug-home", action="store_true",
                    help="salva o HTML da home em ./preview/ e mostra a obra detectada")
    args = ap.parse_args()

    load_dotenv(Path(__file__).with_name(".env"))
    if args.debug_home:
        return debug_home()

    state = {}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            pass
    today = date.today().isoformat()
    if not args.force and not args.dry_run and state.get("date") == today:
        print(f"[{today}] Já enviado hoje ({state.get('asset_id')}). Use --force para reenviar.")
        return 0

    asset_url = args.url or discover_asset_url()
    print(f"Obra: {asset_url}")
    art = fetch_artwork(asset_url)
    img, ctype, ext = download_image(art["image_url"])
    msg = build_message(art, img, ctype, ext)

    if args.dry_run:
        out = Path(__file__).with_name("preview")
        out.mkdir(exist_ok=True)
        (out / f"imagem{ext}").write_bytes(img)
        (out / "email.eml").write_bytes(bytes(msg))
        for label, value in art["rows"]:
            print(f"{label}: {value}")
        print(f"\nPrévia salva em {out}/")
        return 0

    for var in ("SMTP_USER", "SMTP_PASS", "MAIL_TO"):
        if not os.environ.get(var):
            print(f"Variável {var} não definida.", file=sys.stderr)
            return 1

    send(msg)
    STATE_FILE.write_text(json.dumps({"date": today, "asset_id": art["asset_id"]}))
    print(f"[{today}] E-mail enviado para {msg['To']}.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # log simples para uso em cron
        print(f"ERRO: {exc}", file=sys.stderr)
        sys.exit(1)
