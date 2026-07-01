"""Capture des visuels du README : screenshots PNG + GIF de visite guidée.

Reproductible : à chaque évolution de l'UI, une commande régénère tous les
assets du README à taille et cadrage constants, depuis la stack live.

Prérequis (une fois) :
    pip install playwright pillow      # navigateur headless + assemblage GIF
    playwright install chromium        # télécharge le Chromium de capture

Usage (stack démarrée, dashboard en mode live) :
    python scripts/capture_assets.py
    python scripts/capture_assets.py --base-url http://localhost:8501

Sorties dans docs/assets/ :
    screen-overview.png, screen-cold-chain.png, screen-forecast.png,
    screen-copilot.png, screen-data-quality.png, tour.gif,
    screen-grafana.png, screen-dagster.png
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "assets"

# (slug de fichier, chemin URL, libellé pour le log)
PAGES = [
    ("overview",     "/",                  "Vue d'ensemble"),
    ("cold-chain",   "/cold_chain",        "Réfrigérateurs"),
    ("forecast",     "/shortage_forecast", "Prévision des ruptures"),
    ("copilot",      "/clinical_copilot",  "Brief SBAR"),
    ("data-quality", "/data_quality",      "Qualité des données"),
]

VIEWPORT = {"width": 1440, "height": 900}
RENDER_WAIT_S = 6      # Streamlit rend via websocket : on laisse les fragments arriver
GIF_WIDTH = 1600          # large = net (rééchantillonnage Lanczos + palette adaptative)
GIF_FRAME_MS = 2400


def capture(base_url: str) -> list[Path]:
    from playwright.sync_api import sync_playwright

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    shots: list[Path] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=2)
        for slug, path, label in PAGES:
            url = base_url.rstrip("/") + path
            page.goto(url, wait_until="networkidle")
            time.sleep(RENDER_WAIT_S)
            out = OUT_DIR / f"screen-{slug}.png"
            page.screenshot(path=str(out))
            print(f"  {label:<28} -> {out.name}")
            shots.append(out)
        browser.close()
    return shots


def build_gif(shots: list[Path]) -> Path:
    from PIL import Image

    frames = []
    for p in shots:
        img = Image.open(p).convert("RGB")
        ratio = GIF_WIDTH / img.width
        img = img.resize((GIF_WIDTH, round(img.height * ratio)), Image.LANCZOS)
        # Palette adaptative (median cut), sans tramage : texte net, aplats propres.
        frames.append(img.quantize(colors=256, method=Image.Quantize.MEDIANCUT,
                                    dither=Image.Dither.NONE))
    out = OUT_DIR / "tour.gif"
    frames[0].save(
        out, save_all=True, append_images=frames[1:],
        duration=GIF_FRAME_MS, loop=0, optimize=True,
    )
    print(f"  GIF de visite               -> {out.name} "
          f"({out.stat().st_size // 1024} Ko)")
    return out


GRAFANA_DASHBOARD = "/d/coldchain-vigistock?kiosk"   # kiosk : capture sans les menus
DAGSTER_PATH = "/assets"                             # tableau des assets Dagster


def capture_ops(grafana_url: str, dagster_url: str) -> None:
    """Capture Grafana (monitoring temps réel) et Dagster (orchestration).

    Défensif : un échec sur une surface n'interrompt pas l'autre ni la suite.
    """
    from playwright.sync_api import sync_playwright

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        # Grafana : accès anonyme (Viewer) activé côté compose -> le dashboard
        # cold-chain en kiosk s'ouvre sans login. Repli login formulaire si
        # l'anonyme n'est pas dispo (ancienne config).
        try:
            ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=2)
            page = ctx.new_page()
            page.goto(grafana_url.rstrip("/") + GRAFANA_DASHBOARD, wait_until="networkidle")
            time.sleep(2)
            if "/login" in page.url:  # repli : Grafana a renvoyé la page de login
                page.get_by_placeholder("email or username").fill("admin")
                page.get_by_placeholder("password").fill("admin")
                page.get_by_role("button", name="Log in").click()
                page.wait_for_load_state("networkidle")
                for skip in ("Skip", "Skip change password"):
                    try:
                        page.get_by_text(skip).click(timeout=1500)
                        break
                    except Exception:
                        pass
                page.goto(grafana_url.rstrip("/") + GRAFANA_DASHBOARD, wait_until="networkidle")
            time.sleep(RENDER_WAIT_S)
            out = OUT_DIR / "screen-grafana.png"
            page.screenshot(path=str(out))
            print(f"  {'Grafana (cold-chain)':<28} -> {out.name}")
            ctx.close()
        except Exception as exc:
            print(f"  Grafana ignoré : {exc}")

        # Dagster : tableau des assets. On ferme le bandeau onboarding
        # "Dagster University" s'il apparaît (contexte navigateur neuf).
        try:
            page = browser.new_page(viewport=VIEWPORT, device_scale_factor=2)
            page.goto(dagster_url.rstrip("/") + DAGSTER_PATH, wait_until="networkidle")
            time.sleep(RENDER_WAIT_S + 2)
            for label in ("Dismiss", "No thanks", "Close", "Got it"):
                try:
                    page.get_by_role("button", name=label).click(timeout=1500)
                    time.sleep(1)
                    break
                except Exception:
                    pass
            out = OUT_DIR / "screen-dagster.png"
            page.screenshot(path=str(out))
            print(f"  {'Dagster (assets)':<28} -> {out.name}")
        except Exception as exc:
            print(f"  Dagster ignoré : {exc}")

        browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8501",
                        help="URL du dashboard Streamlit (défaut : stack locale)")
    parser.add_argument("--grafana-url", default="http://localhost:3000",
                        help="URL Grafana (défaut : stack locale)")
    parser.add_argument("--dagster-url", default="http://localhost:3001",
                        help="URL Dagster (défaut : stack locale)")
    args = parser.parse_args()
    print(f"Capture depuis {args.base_url} vers {OUT_DIR}")
    shots = capture(args.base_url)
    build_gif(shots)
    capture_ops(args.grafana_url, args.dagster_url)
    print("Terminé : assets prêts pour le README.")


if __name__ == "__main__":
    main()
