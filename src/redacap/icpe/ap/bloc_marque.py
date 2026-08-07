"""Génération du bloc-marque de l'État à partir du modèle SVG `bloc_marque.svg`.

Le bloc-marque (Marianne + intitulé officiel de l'entité + devise) est
rasterisé en PNG à la volée, avec l'intitulé officiel du Préfet injecté
dynamiquement à la place du jeton `__INTITULE_OFFICIEL__` du modèle,
conformément à l'ordre imposé par la charte graphique des services de l'État
(https://www.info.gouv.fr/marque-de-letat/le-bloc-marque) : Marianne, puis
intitulé de l'entité en majuscules, puis la devise « Liberté Égalité
Fraternité » en italique.
"""

from __future__ import annotations

import io
import os
import re
import textwrap
from pathlib import Path
from xml.sax.saxutils import escape

import pypdfium2 as pdfium
from reportlab.graphics import renderPDF
from svglib.svglib import svg2rlg

INTITULE_OFFICIEL_TOKEN = "__INTITULE_OFFICIEL__"
LEGENDE_GROUP_PATTERN = re.compile(
    r'<g[^>]*id="bloc-marque-legende"[^>]*>.*?</g>', re.DOTALL
)
INTITULE_WRAP_WIDTH = 26
MOTTO = ("Liberté", "Égalité", "Fraternité")

# svglib gère mal le positionnement relatif (dy) sur des tspans successifs :
# on calcule donc des positions absolues et on émet des <text> indépendants
# plutôt que d'empiler des tspans dans un seul élément <text>.
INTITULE_Y0 = 58
INTITULE_LINE_HEIGHT = 20
MOTTO_GAP = 26
MOTTO_LINE_HEIGHT = 13

# svglib/reportlab n'ont pas de rasterizer PNG pur Python fiable sur Windows
# (renderPM y requiert la lib native Cairo via rlPyCairo) : on passe donc par
# un PDF intermédiaire, rasterisé avec pypdfium2 (déjà utilisé pour l'OCR).
_RASTER_SCALE = 4.0


def _templates_root_dir() -> Path:
    return Path(os.environ["TEMPLATES_ROOT_DIR"])


def _legende(intitule_officiel: str) -> str:
    """Construit la légende du bloc-marque : intitulé de l'entité puis devise.

    La charte impose l'intitulé de l'entité en majuscules sous la Marianne,
    suivi de la devise « Liberté Égalité Fraternité » en italique. Les lignes
    sont positionnées en absolu (plutôt qu'empilées via `dy` sur des tspans,
    mal supporté par svglib) pour que les intitulés longs, repliés sur
    plusieurs lignes, restent lisibles.
    """
    lignes_intitule = textwrap.wrap(intitule_officiel.upper(), width=INTITULE_WRAP_WIDTH) or [""]
    elements = [
        f'<text x="0" y="{INTITULE_Y0 + i * INTITULE_LINE_HEIGHT}" '
        f'font-size="17" font-weight="700">{escape(ligne)}</text>'
        for i, ligne in enumerate(lignes_intitule)
    ]

    y_motto0 = INTITULE_Y0 + (len(lignes_intitule) - 1) * INTITULE_LINE_HEIGHT + MOTTO_GAP
    elements.extend(
        f'<text x="0" y="{y_motto0 + i * MOTTO_LINE_HEIGHT}" '
        f'font-size="10" font-style="italic">{escape(mot)}</text>'
        for i, mot in enumerate(MOTTO)
    )

    return (
        '<g id="bloc-marque-legende" font-family="Marianne, Arial, sans-serif" '
        'fill="#161616">' + "".join(elements) + "</g>"
    )


def render_bloc_marque_png(intitule_officiel: str) -> bytes:
    """Rend le bloc-marque de l'État en PNG, avec l'intitulé officiel du Préfet injecté."""
    svg_path = _templates_root_dir() / "bloc_marque.svg"
    svg_source = LEGENDE_GROUP_PATTERN.sub(
        lambda _match: _legende(intitule_officiel),
        svg_path.read_text(encoding="utf-8"),
    )

    drawing = svg2rlg(io.StringIO(svg_source))

    pdf_buffer = io.BytesIO()
    renderPDF.drawToFile(drawing, pdf_buffer)
    pdf_buffer.seek(0)

    pdf = pdfium.PdfDocument(pdf_buffer)
    image = pdf[0].render(scale=_RASTER_SCALE).to_pil()

    png_buffer = io.BytesIO()
    image.save(png_buffer, format="PNG")
    return png_buffer.getvalue()
