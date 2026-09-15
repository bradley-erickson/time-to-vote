#!/usr/bin/env python3
"""
Scrape a Survivor Fandom wiki season page ("Castaways" table + starting
tribes) into config/contestants.json and config/tribes.json.

    python scripts/scrape_castaways.py <url>
    python scripts/scrape_castaways.py --html-file page.html

Fandom sits behind Cloudflare's bot challenge, so a plain request from this
script usually gets blocked — you'll see a clear error telling you so. When
that happens: open the page in your own browser, save it (Ctrl+S / Cmd+S ->
"Webpage, HTML only"), and re-run with --html-file pointing at the saved
file. Contestant photos are downloaded from Fandom's separate image CDN,
which isn't behind the same challenge, so that part works either way.

Requires: requests, beautifulsoup4 — pip install -r scripts/requirements.txt
"""
import argparse
import json
import re
import unicodedata
from pathlib import Path

import requests
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
IMAGES_DIR = REPO_ROOT / "static" / "images" / "contestants"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    blocked = resp.status_code != 200 or "Just a moment" in resp.text[:2000]
    if blocked:
        raise SystemExit(
            f"Couldn't fetch {url} directly (status {resp.status_code}).\n"
            "This site is likely behind a bot challenge. Instead: open the page in\n"
            "your browser, save it (Ctrl+S / Cmd+S -> Webpage, HTML only), then run:\n"
            "  python scripts/scrape_castaways.py --html-file <saved.html>"
        )
    return resp.text


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "x"


def parse_tribes(soup: BeautifulSoup) -> list:
    """Starting tribes come from the infobox's "Tribes" field, e.g.
    <a><font style="...background:#5d2c78...">Savu</font></a>."""
    box = soup.find(attrs={"data-source": "tribes"})
    tribes = []
    if not box:
        return tribes
    seen_ids = set()
    for font in box.find_all("font"):
        name = font.get_text(strip=True)
        if not name:
            continue
        style = font.get("style", "")
        match = re.search(r"background:\s*#([0-9a-fA-F]{6})", style)
        color = f"#{match.group(1)}" if match else "#888888"
        tribe_id = base_id = slugify(name)
        n = 2
        while tribe_id in seen_ids:
            tribe_id = f"{base_id}-{n}"
            n += 1
        seen_ids.add(tribe_id)
        tribes.append({"id": tribe_id, "name": name, "color": color})
    return tribes


def bump_image_width(url: str, width: int) -> str:
    return re.sub(r"/scale-to-width-down/\d+", f"/scale-to-width-down/{width}", url)


def parse_castaways(soup: BeautifulSoup, tribes_by_name: dict) -> list:
    heading = soup.find(id="Castaways") or soup.find(
        lambda tag: tag.name in ("h2", "h3")
        and tag.get_text(strip=True).startswith("Castaways")
    )
    if not heading:
        raise SystemExit("Couldn't find a 'Castaways' section on this page.")
    table = heading.find_next("table")
    if not table:
        raise SystemExit("Found the Castaways heading but no table after it.")

    castaways = []
    for row in table.select("tbody > tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        name_link = cells[1].find("a")
        if not name_link:
            continue
        name = name_link.get_text(strip=True)

        img = cells[0].find("img")

        # Bio is "<small>age, hometown<br>occupation</small>" — <br> keeps
        # the two halves as separate strings.
        age = hometown = occupation = None
        bio_tag = cells[1].find("small")
        if bio_tag:
            parts = list(bio_tag.stripped_strings)
            if parts:
                first = [p.strip() for p in parts[0].split(",")]
                age = first[0] or None
                hometown = ", ".join(first[1:]).strip() or None
            if len(parts) > 1:
                occupation = parts[1]

        # Blank pre-season; once tribes are shown on the page, match them
        # against the names we already pulled from the infobox.
        tribe_ids = []
        if len(cells) > 2:
            cell_text = cells[2].get_text(" ", strip=True)
            for tribe_name, tribe_id in tribes_by_name.items():
                if tribe_name.lower() in cell_text.lower():
                    tribe_ids.append(tribe_id)

        castaways.append(
            {
                "name": name,
                "image_url": img.get("src") if img else None,
                "age": age,
                "hometown": hometown,
                "occupation": occupation,
                "tribes": tribe_ids,
            }
        )
    return castaways


def download_image(url: str, dest: Path) -> bool:
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  ! couldn't download {url}: {exc}")
        return False
    dest.write_bytes(resp.content)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url", nargs="?", help="Season page URL")
    parser.add_argument("--html-file", help="Local saved copy of the page (use if the URL is blocked)")
    parser.add_argument("--image-width", type=int, default=300, help="Requested photo width in px (default 300)")
    parser.add_argument("--dry-run", action="store_true", help="Parse and print, but don't write or download anything")
    args = parser.parse_args()

    if not args.url and not args.html_file:
        parser.error("pass a season URL or --html-file <saved page>")

    html = Path(args.html_file).read_text() if args.html_file else fetch_html(args.url)
    soup = BeautifulSoup(html, "html.parser")

    tribes = parse_tribes(soup)
    tribes_by_name = {t["name"]: t["id"] for t in tribes}
    castaways = parse_castaways(soup, tribes_by_name)

    if not castaways:
        raise SystemExit("Found 0 castaways — this page's layout may not match what this script expects.")

    print(f"Found {len(castaways)} castaways and {len(tribes)} tribes.\n")
    for c in castaways:
        note = f" [{', '.join(c['tribes'])}]" if c["tribes"] else ""
        print(f"  {c['name']}{note}")
    print()
    for t in tribes:
        print(f"  tribe: {t['name']} ({t['color']})")

    if args.dry_run:
        print("\n--dry-run: not writing or downloading anything.")
        return

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    contestants = []
    print()
    for i, c in enumerate(castaways, start=1):
        image_path = "/static/images/placeholder.svg"
        if c["image_url"]:
            src = bump_image_width(c["image_url"], args.image_width)
            ext = Path(src.split("?")[0]).suffix or ".png"
            filename = f"{slugify(c['name'])}{ext}"
            print(f"downloading {c['name']}...")
            if download_image(src, IMAGES_DIR / filename):
                image_path = f"/static/images/contestants/{filename}"
        contestants.append(
            {
                "id": f"c{i}",
                "name": c["name"],
                "image": image_path,
                "tribes": c["tribes"],
                "age": c["age"],
                "hometown": c["hometown"],
                "occupation": c["occupation"],
            }
        )

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / "contestants.json").write_text(json.dumps(contestants, indent=2) + "\n")
    (CONFIG_DIR / "tribes.json").write_text(json.dumps(tribes, indent=2) + "\n")

    print(f"\nWrote {len(contestants)} contestants to config/contestants.json")
    print(f"Wrote {len(tribes)} tribes to config/tribes.json")
    print("\nThis OVERWRITES those files — review with `git diff` before committing.")
    print("Any contestant with no tribe shown yet defaults to []; assign it from")
    print("the Settings > Contestants tab once tribes are revealed.")


if __name__ == "__main__":
    main()
