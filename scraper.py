#!/usr/bin/env python3
"""Globoplay -> M3U para SS IPTV.

Descobre os canais publicados no catálogo público do Globoplay e coleta apenas
URLs de mídia que o próprio site disponibiliza ao navegador. Não faz bypass de
login, DRM, assinatura, geoblocking ou qualquer outra restrição.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

CATALOG_URL = "https://globoplay.globo.com/catalogo/"
ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / "channels.json"
M3U_FILE = ROOT / "lista.m3u"

LOGO_DEFAULT = "https://upload.wikimedia.org/wikipedia/commons/7/7d/Globo_logo.png"
ALLOWED_HOSTS = ("globoplay.globo.com", "globo.com")

@dataclass
class Channel:
    id: str
    name: str
    url: str
    category: str
    logo: str = LOGO_DEFAULT
    page_url: str = ""


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def slug(value: str) -> str:
    value = re.sub(r"[^\w\-]+", "-", value, flags=re.UNICODE)
    return value.strip("-").lower() or "canal"


def canonical_url(url: str) -> str:
    try:
        p = urlparse(url)
        return f"{p.scheme.lower()}://{p.netloc.lower()}{p.path}"
    except Exception:
        return url


def valid_stream_url(url: str) -> bool:
    try:
        p = urlparse(url)
        if p.scheme not in {"http", "https"}:
            return False
        path = p.path.lower()
        low = url.lower()
        return (
            any(x in path for x in (".m3u8", ".mpd", "/manifest", "/playlist"))
            or "m3u8" in low
        )
    except Exception:
        return False


def media_urls_from_page(page) -> list[str]:
    urls: list[str] = []

    try:
        urls.extend(page.evaluate("""() => performance.getEntriesByType('resource').map(x => x.name)"""))
    except Exception:
        pass

    try:
        urls.extend(page.evaluate("""() => {
            const out = [];
            for (const el of document.querySelectorAll('video, audio, source')) {
                if (el.src) out.push(el.src);
                if (el.currentSrc) out.push(el.currentSrc);
            }
            return out;
        }"""))
    except Exception:
        pass

    try:
        html = page.content()
        for pattern in (
            r'https?://[^"\\\'\s<>]+?\.m3u8(?:\?[^"\\\'\s<>]*)?',
            r'https?://[^"\\\'\s<>]+?\.mpd(?:\?[^"\\\'\s<>]*)?',
        ):
            urls.extend(re.findall(pattern, html, flags=re.I))
    except Exception:
        pass

    result: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if not isinstance(url, str):
            continue
        url = url.replace("\\u0026", "&").replace("\\/", "/").rstrip(".,;)")
        if url in seen or not valid_stream_url(url):
            continue
        seen.add(url)
        result.append(url)
    return result


def discover_catalog_pages(page) -> list[tuple[str, str, str]]:
    """Retorna (nome, categoria, URL) para as páginas de canais do catálogo."""
    page.goto(CATALOG_URL, wait_until="domcontentloaded", timeout=90_000)
    try:
        page.wait_for_load_state("networkidle", timeout=25_000)
    except PlaywrightTimeoutError:
        pass
    page.wait_for_timeout(4_000)

    items: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    links = page.locator('a[href*="/canais/"]')
    count = links.count()
    for i in range(count):
        a = links.nth(i)
        try:
            href = a.get_attribute("href") or ""
            text = clean(a.inner_text())
        except Exception:
            continue
        if not href or not text:
            continue
        if href.startswith("/"):
            href = "https://globoplay.globo.com" + href
        if not href.startswith("https://globoplay.globo.com/canais/"):
            continue
        href = href.split("#", 1)[0]
        if href in seen:
            continue
        seen.add(href)
        items.append((text, text, href))

    # Algumas versões do catálogo podem usar links que não tenham /canais/.
    # Incluímos somente páginas do próprio Globoplay explicitamente marcadas
    # como ao-vivo, evitando capturar vídeos/programas do catálogo.
    if not items:
        links = page.locator('a[href*="/ao-vivo/"]')
        count = links.count()
        for i in range(count):
            a = links.nth(i)
            try:
                href = a.get_attribute("href") or ""
                text = clean(a.inner_text())
            except Exception:
                continue
            if href.startswith("/"):
                href = "https://globoplay.globo.com" + href
            if "/ao-vivo/" not in href or not text:
                continue
            href = href.split("#", 1)[0]
            if href in seen:
                continue
            seen.add(href)
            items.append((text, text, href))

    # Se a página mudar e deixar de expor os links, não apagamos uma lista
    # anterior válida.
    return items


def extract_channel(page, name: str, category: str, page_url: str) -> list[Channel]:
    logging.info("Consultando %s", name)
    try:
        responses: list[str] = []

        def on_response(response):
            url = response.url
            if valid_stream_url(url):
                responses.append(url)

        page.on("response", on_response)
        page.goto(page_url, wait_until="domcontentloaded", timeout=90_000)
        try:
            page.wait_for_load_state("networkidle", timeout=20_000)
        except PlaywrightTimeoutError:
            pass
        page.wait_for_timeout(4_000)
        urls = responses + media_urls_from_page(page)
        page.remove_listener("response", on_response)
    except Exception as exc:
        logging.warning("Falha em %s: %s", page_url, exc)
        return []

    unique_urls: list[str] = []
    seen: set[str] = set()
    for url in urls:
        key = canonical_url(url)
        if key in seen:
            continue
        seen.add(key)
        unique_urls.append(url)

    result: list[Channel] = []
    for idx, url in enumerate(unique_urls, 1):
        suffix = f" {idx}" if len(unique_urls) > 1 else ""
        result.append(Channel(
            id=f"globoplay-{slug(name)}-{idx}",
            name=f"{name}{suffix}",
            url=url,
            category=category or name,
            page_url=page_url,
        ))
    return result


def load_state() -> list[Channel]:
    if not STATE_FILE.exists():
        return []
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return [Channel(**x) for x in data]
    except Exception as exc:
        logging.warning("Não foi possível ler %s: %s", STATE_FILE, exc)
        return []


def save_state(channels: list[Channel]) -> None:
    STATE_FILE.write_text(
        json.dumps([asdict(c) for c in channels], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def merge(current: list[Channel], previous: list[Channel]) -> list[Channel]:
    """Substitui a lista pelos canais efetivamente encontrados.

    O estado anterior é usado somente para preservar metadados estáveis quando
    a URL canônica do stream reaparece com tokens temporários diferentes.
    Canais que não forem encontrados são removidos.
    """
    previous_by_canonical = {canonical_url(c.url): c for c in previous}
    result: list[Channel] = []
    seen: set[str] = set()

    for c in current:
        key = canonical_url(c.url)
        if key in seen:
            continue
        seen.add(key)
        old = previous_by_canonical.get(key)
        if old:
            c.name = c.name or old.name
            c.category = c.category or old.category
            c.logo = old.logo or c.logo
            c.id = old.id
        result.append(c)

    return result


def write_m3u(channels: list[Channel]) -> None:
    lines = ["#EXTM3U"]
    grouped: dict[str, list[Channel]] = {}
    for c in channels:
        grouped.setdefault(c.category or "Globoplay", []).append(c)

    for category in sorted(grouped, key=str.casefold):
        for c in sorted(grouped[category], key=lambda x: x.name.casefold()):
            safe_name = clean(c.name).replace('"', "'")
            safe_category = clean(category).replace('"', "'")
            safe_logo = c.logo.replace('"', "'")
            lines.append(
                f'#EXTINF:-1 tvg-id="{c.id}" tvg-name="{safe_name}" '
                f'tvg-logo="{safe_logo}" group-title="{safe_category}",{safe_name}'
            )
            lines.append(c.url)

    M3U_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    previous = load_state()

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
            )
            catalog_page = context.new_page()
            pages = discover_catalog_pages(catalog_page)
            logging.info("Canais encontrados no catálogo: %d", len(pages))

            if not pages:
                raise RuntimeError("O catálogo não expôs páginas de canais.")

            current: list[Channel] = []
            for name, category, url in pages:
                channel_page = context.new_page()
                current.extend(extract_channel(channel_page, name, category, url))
                channel_page.close()

            browser.close()

    except Exception as exc:
        logging.error("Falha ao consultar o Globoplay: %s", exc)
        if previous:
            logging.warning("Preservando a última lista válida (%d canais).", len(previous))
            write_m3u(previous)
            return 0
        return 1

    if not current:
        logging.error("Nenhum stream utilizável foi exposto pelo Globoplay.")
        if previous:
            write_m3u(previous)
            return 0
        return 2

    merged = merge(current, previous)
    save_state(merged)
    write_m3u(merged)
    logging.info("Lista atualizada: %d stream(s), %d página(s) de canal.", len(merged), len(pages))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
