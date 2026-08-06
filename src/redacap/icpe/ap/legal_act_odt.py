"""Rendition d'un LegalAct au format ODT (OpenDocument Text)."""

from __future__ import annotations

from odf.opendocument import OpenDocumentText
from odf.text import H, List, ListItem, P

from redacap.icpe.ap.legal_act import LegalAct


def _add_bullet_list(doc: OpenDocumentText, items: list[str]) -> None:
    """Ajoute une liste à puces au document, un élément par item."""
    bullet_list = List()
    for item_text in items:
        item = ListItem()
        item.addElement(P(text=item_text))
        bullet_list.addElement(item)
    doc.text.addElement(bullet_list)


def render_legal_act_odt(act: LegalAct, filepath: str) -> None:
    """Rend un LegalAct en document ODT et l'enregistre à l'emplacement indiqué."""
    doc = OpenDocumentText()

    entete = act.type_acte.value.replace("_", " ").upper()
    if act.numero:
        entete = f"{entete} N° {act.numero}"
    doc.text.addElement(H(outlinelevel=1, text=entete))

    if act.titre:
        doc.text.addElement(H(outlinelevel=2, text=act.titre))

    if act.prefecture:
        doc.text.addElement(P(text=f"Préfecture : {act.prefecture}"))
    if act.etablissement:
        doc.text.addElement(
            P(
                text=(
                    f"Établissement : {act.etablissement.raison_sociale}, "
                    f"{act.etablissement.adresse}, {act.etablissement.commune}"
                )
            )
        )
    doc.text.addElement(P(text=act.objet))

    if act.visas:
        doc.text.addElement(H(outlinelevel=2, text="Vu"))
        _add_bullet_list(doc, act.visas)

    if act.considerants:
        doc.text.addElement(H(outlinelevel=2, text="Considérant"))
        _add_bullet_list(doc, act.considerants)

    doc.text.addElement(H(outlinelevel=2, text="ARRÊTE"))

    for article in act.articles:
        titre_article = article.numero
        if article.titre:
            titre_article = f"{titre_article} — {article.titre}"
        doc.text.addElement(H(outlinelevel=3, text=titre_article))
        for paragraphe in article.contenu.split("\n"):
            if paragraphe.strip():
                doc.text.addElement(P(text=paragraphe.strip()))

    if act.signataire:
        doc.text.addElement(P(text=act.signataire))

    doc.save(filepath)
