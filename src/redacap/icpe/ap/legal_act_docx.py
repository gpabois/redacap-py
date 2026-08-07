"""Rendition d'un LegalAct au format DOCX, à partir du modèle `legal_act.docx`."""

from __future__ import annotations

import io
import os
from pathlib import Path

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

from redacap.icpe.ap.bloc_marque import render_bloc_marque_png
from redacap.icpe.ap.legal_act import LegalAct

INTITULE_PREFET_PAR_DEFAUT = "PRÉFET"
DREAL_PAR_DEFAUT = "DREAL"


def _templates_root_dir() -> Path:
    return Path(os.environ["TEMPLATES_ROOT_DIR"])


def render_legal_act_docx(act: LegalAct, filepath: str) -> None:
    """Rend un LegalAct en document DOCX à partir du modèle `legal_act.docx` et l'enregistre."""
    tpl = DocxTemplate(str(_templates_root_dir() / "legal_act.docx"))


    context = {
        "timbre_adm": act.dreal or DREAL_PAR_DEFAUT,
        "numero": act.numero,
        "type_acte": act.type_acte.value.replace("_", " ").upper(),
        "titre": act.titre,
        "prefecture": act.prefecture,
        "departement": act.departement,
        "signataire": act.signataire,
        "etablissement": act.etablissement.model_dump() if act.etablissement else None,
        "objet": act.objet,
        "visas": act.visas,
        "considerants": act.considerants,
        "articles": [article.model_dump() for article in act.articles],
        "voies_recours": act.voies_recours,
        "date_signature": act.date_signature.strftime("%d/%m/%Y") if act.date_signature else None,
    }

    tpl.render(context)
    tpl.save(filepath)
