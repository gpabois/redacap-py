"""LangGraph single-node graph template.

Returns a predefined response. Replace logic and configuration as needed.
"""

from __future__ import annotations

import asyncio
import base64
import io
import operator
from dataclasses import dataclass
from typing import Annotated, Any, Dict, List, Optional

import pypdfium2 as pdfium
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph
from langgraph.types import Send, interrupt
from langgraph.runtime import Runtime
from typing_extensions import TypedDict


from redacap.icpe.ap.med.agents import (
    RaisonMiseEnDemeure,
    VerificationDetaillee,
    analyse_mise_en_demeure,
    redaction_article_premier,
    redaction_articles_suivants,
    redaction_considerants,
    redaction_titre,
    redaction_visas,
    structuration_rapport_inspection,
    verificateur_article_premier,
    verificateur_articles_suivants,
    verificateur_considerants,
    verificateur_titre,
    verificateur_visas,
)
from redacap.icpe.ap.med.conception_raison_mise_en_demeure import (
    StateConceptionRaison,
    conception_raison_mise_en_demeure,
)
from redacap.icpe.ap.legal_act import Article, LegalAct, TypeActe
from redacap.icpe.ap.legal_act_odt import render_legal_act_odt
from redacap.icpe.report import Constat, InspectionReport
from redacap.model import ocr_model

OCR_PROMPT = (
    "Transcris fidèlement tout le texte visible sur cette page, y compris "
    "les tableaux et en-têtes, sans commentaire ni reformulation."
)

MAX_TENTATIVES_REDACTION = 20

class Context(TypedDict):
    """Context parameters for the agent.

    Set these when creating assistants OR when invoking the graph.
    See: https://langchain-ai.github.io/langgraph/cloud/how-tos/configuration_cloud/
    """

    my_configurable_param: str

class StateMiseEnDemeure(TypedDict):
    """Input state for the agent.

    Defines the initial structure of incoming data.
    See: https://langchain-ai.github.io/langgraph/concepts/low_level/#state
    """
    report: Optional[InspectionReport]
    report_filepath: Optional[str]
    report_pages: List[str]
    act: Optional[LegalAct]
    acte_legal_output_filepath: Optional[str]
    raisons: list[RaisonMiseEnDemeure]
    titre: Optional[str]
    visas: List[str]
    considerants: List[str]
    article_premier: Optional[Article]
    articles_suivants: List[Article]
    resultats_conception_raisons: Annotated[List[Dict[str, Any]], operator.add]
    raisons_supprimees: List[Dict[str, Any]]
    verification_titre: Optional[VerificationDetaillee]
    verification_visas: Optional[VerificationDetaillee]
    verification_considerants: Optional[VerificationDetaillee]
    verification_article_premier: Optional[VerificationDetaillee]
    verification_articles_suivants: Optional[VerificationDetaillee]
    tentatives_titre: int
    tentatives_visas: int
    tentatives_considerants: int
    tentatives_article_premier: int
    tentatives_articles_suivants: int


async def check_inspection_report(state: StateMiseEnDemeure):
    return state.get("report") is not None

async def ask_inspection_report(state: StateMiseEnDemeure):
    if not state.get("report_filepath"):
        report_filepath = interrupt("Donner le chemin vers le rapport d'inspection")
    else:
        report_filepath = state.get("report_filepath")
        
    return {"report_filepath": report_filepath}

async def extract_inspection_report(state: StateMiseEnDemeure) -> Dict[str, Any]:
    """OCR each page of the inspection report PDF, unless already extracted."""
    report_pages = state.get("report_pages")

    if report_pages:
        return {"report_pages": report_pages}

    pdf = pdfium.PdfDocument(state["report_filepath"])
    ocred_pages = []
    for page in pdf:
        buffer = io.BytesIO()
        page.render(scale=2.0).to_pil().save(buffer, format="PNG")
        image_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        response = await ocr_model.ainvoke(
            [
                HumanMessage(
                    content=[
                        {"type": "text", "text": OCR_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                        },
                    ]
                )
            ]
        )
        ocred_pages.append(response.content)

    return {"report_pages": ocred_pages}


def _join_report_pages(report_pages: List[str]) -> str:
    """Join the OCR'd report pages into a single, page-labeled text block."""
    return "\n\n".join(
        f"--- Page {i + 1} ---\n{page}" for i, page in enumerate(report_pages)
    )


async def structure_inspection_report(state: StateMiseEnDemeure) -> Dict[str, Any]:
    """Structure the OCR'd report pages into an InspectionReport."""
    report_text = _join_report_pages(state["report_pages"])
    report = await structuration_rapport_inspection.ainvoke(report_text)
    return {"report": report}


def _iter_constats(report: Optional[InspectionReport]) -> List[Constat]:
    """Aplatit les constats de tous les points de contrôle du rapport, dans l'ordre."""
    if not report:
        return []
    return [constat for point in report.points_de_controle for constat in point.constats]


def _format_constats_numerotes(report: Optional[InspectionReport]) -> str:
    """Numérote les constats structurés du rapport pour permettre leur référencement."""
    constats = _iter_constats(report)
    if not constats:
        return ""

    blocks = [
        f"{i}. [{constat.thematique}] {constat.description}"
        for i, constat in enumerate(constats, start=1)
    ]
    return "Constats numérotés du rapport :\n" + "\n".join(blocks) + "\n\n"


async def extract_raisons_mise_en_demeure(state: StateMiseEnDemeure) -> Dict[str, Any]:
    """Aggregate the OCR'd report pages and extract the mise en demeure reasons."""
    report_text = _join_report_pages(state["report_pages"])
    report = state.get("report")
    report_context = (
        f"Synthèse structurée du rapport :\n{report.model_dump_json(indent=2)}\n\n"
        if report
        else ""
    )
    constats_context = _format_constats_numerotes(report)
    result = await analyse_mise_en_demeure.ainvoke(
        f"{report_context}{constats_context}{report_text}"
    )
    return {"raisons": [raison.model_dump() for raison in result.raisons]}


def _format_raisons(raisons: list[RaisonMiseEnDemeure]) -> str:
    """Serialize the extracted raisons into a readable block for prompting."""
    blocks = []
    for i, raison in enumerate(raisons, start=1):
        blocks.append(
            f"Raison {i} :\n"
            f"- Synthèse : {raison['synthèse']}\n"
            f"- Disposition non respectée : {raison['disposition']}\n"
            f"- Référence : {raison['reference_article']} ({raison['reference_source']})\n"
            f"- Action demandée : {raison.get('action') or 'non précisée'}\n"
            f"- Délai : {raison['delai_valeur']} {raison['délai_unité']}"
        )
    return "\n\n".join(blocks)


def _format_drafting_context(state: StateMiseEnDemeure) -> str:
    """Serialize l'établissement et les raisons pour les agents de rédaction."""
    report = state.get("report")
    etablissement_block = (
        f"Établissement concerné :\n{report.etablissement.model_dump_json(indent=2)}\n\n"
        f"Date d'inspection: {report.date_inspection}"
        if report
        else ""
    )
    return f"{etablissement_block}{_format_raisons(state['raisons'])}"


def _resoudre_constat(report: Optional[InspectionReport], raison: Dict[str, Any]) -> Optional[Constat]:
    """Retrouve le constat structuré du rapport lié à une raison, si disponible."""
    numero = raison.get("constat_numero")
    if not report or not numero:
        return None
    constats = _iter_constats(report)
    index = numero - 1
    if 0 <= index < len(constats):
        return constats[index]
    return None


def dispatch_conception_raisons(state: StateMiseEnDemeure) -> List[Any]:
    """Distribue chaque raison extraite, avec son constat lié, à une instance du sous-graphe.

    S'il n'y a aucune raison à traiter, court-circuite directement vers
    l'agrégation : sans cela, aucun `Send` ne serait émis, "conception_raison"
    ne s'exécuterait jamais, et le reste du graphe (rédaction, vérification,
    intégration finale) resterait bloqué indéfiniment sans erreur visible.
    """
    if not state["raisons"]:
        return ["applique_resultats_conception_raisons"]
    report = state.get("report")
    return [
        Send(
            "conception_raison",
            {
                "constat": _resoudre_constat(report, raison),
                "raison": RaisonMiseEnDemeure(**raison),
                "verification": None,
                "tentatives": 0,
                "action": None,
                "motif_suppression": None,
            },
        )
        for raison in state["raisons"]
    ]


async def conception_raison(state: StateConceptionRaison) -> Dict[str, Any]:
    """Exécute le sous-graphe de conception pour une raison, et remonte son résultat."""
    resultat = await conception_raison_mise_en_demeure.ainvoke(state)
    return {"resultats_conception_raisons": [resultat]}


def _regrouper_par_source(raisons: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Réordonne les raisons pour que celles partageant la même source légale soient contiguës.

    L'ordre d'apparition des sources et l'ordre relatif des raisons au sein
    d'une même source sont préservés ; seul le regroupement par source change.
    """
    groupes: Dict[str, List[Dict[str, Any]]] = {}
    ordre_sources: List[str] = []
    for raison in raisons:
        source = raison["reference_source"]
        if source not in groupes:
            groupes[source] = []
            ordre_sources.append(source)
        groupes[source].append(raison)
    return [raison for source in ordre_sources for raison in groupes[source]]


async def applique_resultats_conception_raisons(state: StateMiseEnDemeure) -> Dict[str, Any]:
    """Met à jour les raisons retenues à partir des résultats des sous-graphes de conception."""
    raisons_retenues: List[Dict[str, Any]] = []
    raisons_supprimees: List[Dict[str, Any]] = []
    for resultat in state.get("resultats_conception_raisons", []):
        raison = resultat["raison"]
        if resultat.get("action") == "supprimer":
            raisons_supprimees.append(
                {
                    "raison": raison.model_dump(),
                    "motif_suppression": resultat.get("motif_suppression"),
                }
            )
        else:
            raisons_retenues.append(raison.model_dump())
    return {
        "raisons": _regrouper_par_source(raisons_retenues),
        "raisons_supprimees": raisons_supprimees,
    }


def _conforme(verification: Optional[VerificationDetaillee]) -> bool:
    """Calcule la conformité globale à partir des verdicts unitaires du vérificateur.

    Le modèle ne renvoie plus de booléen global ni de liste d'anomalies : il
    juge chaque point de contrôle indépendamment, et c'est ici qu'on agrège
    ces verdicts. Une liste vide est conforme (aucun point non conforme).
    """
    return verification is not None and all(
        resultat.conforme for resultat in verification.resultats
    )


def _format_correction_feedback(verification: Optional[VerificationDetaillee]) -> str:
    """Formate les points non conformes relevés par un vérificateur en demande de correction."""
    if not verification or _conforme(verification):
        return ""
    anomalies = "\n".join(
        f"- {resultat.analyse}" for resultat in verification.resultats if not resultat.conforme
    )
    return (
        "\n\n---\n\nLa version précédente de ce contenu a été jugée non conforme par "
        f"le contrôle qualité, pour les raisons suivantes :\n{anomalies}\n\n"
        "Corrige ces anomalies dans la nouvelle version, en conservant ce qui était "
        "déjà correct."
    )


async def redige_titre(state: StateMiseEnDemeure) -> Dict[str, Any]:
    """Draft the title of the mise en demeure."""
    feedback = _format_correction_feedback(state.get("verification_titre"))
    result = await redaction_titre.ainvoke(_format_drafting_context(state) + feedback)
    return {"titre": result.titre}


async def redige_visas(state: StateMiseEnDemeure) -> Dict[str, Any]:
    """Draft the "Vu ..." legal references of the mise en demeure."""
    feedback = _format_correction_feedback(state.get("verification_visas"))
    result = await redaction_visas.ainvoke(_format_drafting_context(state) + feedback)
    return {"visas": result.visas}


async def redige_considerants(state: StateMiseEnDemeure) -> Dict[str, Any]:
    """Draft the considérants motivating the mise en demeure."""
    feedback = _format_correction_feedback(state.get("verification_considerants"))
    result = await redaction_considerants.ainvoke(_format_drafting_context(state) + feedback)
    return {"considerants": result.considerants}


async def redige_article_premier(state: StateMiseEnDemeure) -> Dict[str, Any]:
    """Draft Article 1er — the core injunction — of the mise en demeure."""
    feedback = _format_correction_feedback(state.get("verification_article_premier"))
    article = await redaction_article_premier.ainvoke(_format_drafting_context(state) + feedback)
    return {"article_premier": article}


async def redige_articles_suivants(state: StateMiseEnDemeure) -> Dict[str, Any]:
    """Draft the remaining articles (voie de recours, notification)."""
    feedback = _format_correction_feedback(state.get("verification_articles_suivants"))
    result = await redaction_articles_suivants.ainvoke(_format_drafting_context(state) + feedback)
    return {"articles_suivants": result.articles}


def _format_verification_input(state: StateMiseEnDemeure, contenu_a_verifier: str) -> str:
    """Combine le contexte de rédaction et le contenu à vérifier pour un vérificateur."""
    return (
        f"{_format_drafting_context(state)}\n\n---\n\n"
        f"Contenu à vérifier :\n{contenu_a_verifier}"
    )


async def verifie_titre(state: StateMiseEnDemeure) -> Dict[str, Any]:
    """Control that the drafted titre complies with the drafting instructions."""
    result = await verificateur_titre.ainvoke(
        _format_verification_input(state, state["titre"])
    )
    return {
        "verification_titre": result,
        "tentatives_titre": state.get("tentatives_titre", 0) + 1,
    }


async def verifie_visas(state: StateMiseEnDemeure) -> Dict[str, Any]:
    """Control that the drafted visas comply with the drafting instructions."""
    contenu = "\n".join(f"- {visa}" for visa in state["visas"])
    result = await verificateur_visas.ainvoke(_format_verification_input(state, contenu))
    return {
        "verification_visas": result,
        "tentatives_visas": state.get("tentatives_visas", 0) + 1,
    }


async def verifie_considerants(state: StateMiseEnDemeure) -> Dict[str, Any]:
    """Control that the drafted considérants comply with the drafting instructions."""
    contenu = "\n".join(f"- {considerant}" for considerant in state["considerants"])
    result = await verificateur_considerants.ainvoke(_format_verification_input(state, contenu))
    return {
        "verification_considerants": result,
        "tentatives_considerants": state.get("tentatives_considerants", 0) + 1,
    }


async def verifie_article_premier(state: StateMiseEnDemeure) -> Dict[str, Any]:
    """Control that the drafted article premier complies with the drafting instructions."""
    contenu = state["article_premier"].model_dump_json(indent=2)
    result = await verificateur_article_premier.ainvoke(
        _format_verification_input(state, contenu)
    )
    return {
        "verification_article_premier": result,
        "tentatives_article_premier": state.get("tentatives_article_premier", 0) + 1,
    }


async def verifie_articles_suivants(state: StateMiseEnDemeure) -> Dict[str, Any]:
    """Control that the drafted articles suivants comply with the drafting instructions."""
    contenu = "\n\n".join(
        article.model_dump_json(indent=2) for article in state["articles_suivants"]
    )
    result = await verificateur_articles_suivants.ainvoke(
        _format_verification_input(state, contenu)
    )
    return {
        "verification_articles_suivants": result,
        "tentatives_articles_suivants": state.get("tentatives_articles_suivants", 0) + 1,
    }


def _route_apres_verification(verification_key: str, tentatives_key: str):
    """Construit la fonction de routage post-vérification pour une section donnée.

    Renvoie True (contenu intégré tel quel) si la vérification est conforme ou si
    le nombre maximal de tentatives de correction est atteint ; False (retour au
    rédacteur avec les anomalies relevées) sinon.
    """

    async def _route(state: StateMiseEnDemeure) -> bool:
        if _conforme(state.get(verification_key)):
            return True
        return state.get(tentatives_key, 0) >= MAX_TENTATIVES_REDACTION

    return _route


route_apres_verification_titre = _route_apres_verification(
    "verification_titre", "tentatives_titre"
)
route_apres_verification_visas = _route_apres_verification(
    "verification_visas", "tentatives_visas"
)
route_apres_verification_considerants = _route_apres_verification(
    "verification_considerants", "tentatives_considerants"
)
route_apres_verification_article_premier = _route_apres_verification(
    "verification_article_premier", "tentatives_article_premier"
)
route_apres_verification_articles_suivants = _route_apres_verification(
    "verification_articles_suivants", "tentatives_articles_suivants"
)


async def integre_acte_legal(state: StateMiseEnDemeure) -> Dict[str, Any]:
    """Assemble dans le LegalAct final le contenu produit par les rédacteurs.

    Ce nœud n'est atteint, pour chaque section, qu'après que le routeur de
    vérification a décidé de la laisser passer (conforme, ou nombre maximal
    de tentatives de correction atteint) : on intègre donc ce contenu tel
    quel, sans le re-filtrer sur la conformité ici. Re-vérifier `_conforme`
    à ce stade contredirait la décision du routeur et ferait disparaître
    silencieusement tout contenu qui n'a pas convergé avant l'épuisement des
    tentatives.
    """
    report = state.get("report")
    etablissement = report.etablissement if report else None

    articles: List[Article] = []
    article_premier = state.get("article_premier")

    if article_premier:
        articles.append(article_premier)

    articles.extend(state.get("articles_suivants", []))

    visas = state.get("visas", [])
    considerants = state.get("considerants", [])

    objet = (
        f"Mise en demeure de la société {etablissement.raison_sociale} de se "
        "conformer à la réglementation applicable à son installation classée"
        if etablissement
        else "Mise en demeure de mise en conformité"
    )

    act = LegalAct(
        type_acte=TypeActe.MISE_EN_DEMEURE,
        etablissement=etablissement,
        titre=state.get("titre"),
        objet=objet,
        visas=visas,
        considerants=considerants,
        articles=articles,
        rubriques=etablissement.rubriques if etablissement else [],
    )
    return {"act": act}


async def rendition_acte_legal_odt(state: StateMiseEnDemeure) -> Dict[str, Any]:
    """Rend le LegalAct en ODT et l'enregistre à l'emplacement demandé à l'utilisateur."""
    if not state.get("acte_legal_output_filepath"):
        output_filepath = interrupt("Donner le chemin de sauvegarde du fichier ODT de l'arrêté")
    else:
        output_filepath = state.get("acte_legal_output_filepath")

    await asyncio.to_thread(render_legal_act_odt, state["act"], output_filepath)

    return {"acte_legal_output_filepath": output_filepath}

# Define the graph
graph = (
    StateGraph(StateMiseEnDemeure, context_schema=Context)
    .add_node(check_inspection_report)
    .add_node(ask_inspection_report)
    .add_node(extract_inspection_report)
    .add_node(structure_inspection_report)
    .add_node(extract_raisons_mise_en_demeure)
    .add_node(conception_raison)
    .add_node(applique_resultats_conception_raisons)
    .add_node(redige_titre)
    .add_node(redige_visas)
    .add_node(redige_considerants)
    .add_node(redige_article_premier)
    .add_node(redige_articles_suivants)
    .add_node(verifie_titre)
    .add_node(verifie_visas)
    .add_node(verifie_considerants)
    .add_node(verifie_article_premier)
    .add_node(verifie_articles_suivants)
    .add_node(integre_acte_legal)
    .add_node(rendition_acte_legal_odt)
    .add_conditional_edges("__start__", check_inspection_report, {True: "extract_raisons_mise_en_demeure", False: "ask_inspection_report"})
    .add_edge("ask_inspection_report", "extract_inspection_report")
    .add_edge("extract_inspection_report", "structure_inspection_report")
    .add_edge("structure_inspection_report", "extract_raisons_mise_en_demeure")
    .add_conditional_edges(
        "extract_raisons_mise_en_demeure",
        dispatch_conception_raisons,
        ["conception_raison", "applique_resultats_conception_raisons"],
    )
    .add_edge("conception_raison", "applique_resultats_conception_raisons")
    .add_edge("applique_resultats_conception_raisons", "redige_titre")
    .add_edge("applique_resultats_conception_raisons", "redige_visas")
    .add_edge("applique_resultats_conception_raisons", "redige_considerants")
    .add_edge("applique_resultats_conception_raisons", "redige_article_premier")
    .add_edge("applique_resultats_conception_raisons", "redige_articles_suivants")
    .add_edge("redige_titre", "verifie_titre")
    .add_edge("redige_visas", "verifie_visas")
    .add_edge("redige_considerants", "verifie_considerants")
    .add_edge("redige_article_premier", "verifie_article_premier")
    .add_edge("redige_articles_suivants", "verifie_articles_suivants")
    .add_conditional_edges(
        "verifie_titre",
        route_apres_verification_titre,
        {True: "integre_acte_legal", False: "redige_titre"},
    )
    .add_conditional_edges(
        "verifie_visas",
        route_apres_verification_visas,
        {True: "integre_acte_legal", False: "redige_visas"},
    )
    .add_conditional_edges(
        "verifie_considerants",
        route_apres_verification_considerants,
        {True: "integre_acte_legal", False: "redige_considerants"},
    )
    .add_conditional_edges(
        "verifie_article_premier",
        route_apres_verification_article_premier,
        {True: "integre_acte_legal", False: "redige_article_premier"},
    )
    .add_conditional_edges(
        "verifie_articles_suivants",
        route_apres_verification_articles_suivants,
        {True: "integre_acte_legal", False: "redige_articles_suivants"},
    )
    .add_edge("integre_acte_legal", "rendition_acte_legal_odt")
    .compile(name="RedactMiseEnDemeure")
)
