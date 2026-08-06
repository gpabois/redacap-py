"""Sous-graphe de conception d'une raison de mise en demeure.

Applique une boucle rédaction/vérification à une seule raison : la rédaction
affine la raison (et corrige les anomalies relevées), la vérification décide
si elle est conforme, à corriger, ou à supprimer (non-conformité non avérée).
Le sous-graphe se termine soit en conservant la raison affinée, soit en
ordonnant sa suppression avec le motif correspondant.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from redacap.icpe.ap.med.agents import (
    DecisionRaison,
    RaisonMiseEnDemeure,
    VerificationRaison,
    redaction_raison_mise_en_demeure,
    verificateur_raison_mise_en_demeure,
)
from redacap.icpe.report import Constat

MAX_TENTATIVES_RAISON = 3


class StateConceptionRaison(TypedDict):
    """État du sous-graphe de conception d'une raison de mise en demeure."""

    constat: Optional[Constat]
    raison: RaisonMiseEnDemeure
    verification: Optional[VerificationRaison]
    tentatives: int
    action: Optional[str]
    motif_suppression: Optional[str]


def _format_raison_input(state: StateConceptionRaison, feedback: str = "") -> str:
    """Combine le constat lié et la raison courante pour les agents.

    Volontairement limité au constat et à la raison (pas le rapport entier) :
    ce contexte est dupliqué à chaque appel de sous-graphe (un par raison), le
    réinjecter en entier gonflerait inutilement la consommation de tokens.
    """
    constat = state.get("constat")
    constat_block = (
        "Point de constat de l'inspection lié à cette raison :\n"
        f"{constat.model_dump_json(indent=2)}\n\n---\n\n"
        if constat
        else ""
    )
    raison_json = state["raison"].model_dump_json(indent=2)
    return f"{constat_block}Raison à traiter :\n{raison_json}{feedback}"


async def redige_raison(state: StateConceptionRaison) -> Dict[str, Any]:
    """Affine la raison, en corrigeant les anomalies relevées le cas échéant."""
    verification = state.get("verification")
    feedback = ""
    if verification and verification.decision == DecisionRaison.A_CORRIGER:
        anomalies = "\n".join(f"- {anomalie}" for anomalie in verification.anomalies)
        feedback = (
            "\n\n---\n\nCette raison a été jugée à corriger par le contrôle qualité, "
            f"pour les raisons suivantes :\n{anomalies}\n\nCorrige-la en conséquence."
        )
    raison = await redaction_raison_mise_en_demeure.ainvoke(_format_raison_input(state, feedback))
    return {"raison": raison}


async def verifie_raison(state: StateConceptionRaison) -> Dict[str, Any]:
    """Contrôle la raison affinée et décide de la conserver, la corriger ou la supprimer."""
    verification = await verificateur_raison_mise_en_demeure.ainvoke(
        _format_raison_input(state)
    )
    return {
        "verification": verification,
        "tentatives": state.get("tentatives", 0) + 1,
    }


async def route_apres_verification_raison(state: StateConceptionRaison) -> str:
    """Décide de conserver, corriger à nouveau, ou supprimer la raison."""
    verification = state["verification"]
    if verification.decision == DecisionRaison.A_SUPPRIMER:
        return "supprimer_raison"
    if verification.decision == DecisionRaison.CONFORME:
        return "conserver_raison"
    if state.get("tentatives", 0) >= MAX_TENTATIVES_RAISON:
        return "conserver_raison"
    return "redige_raison"


async def conserver_raison(state: StateConceptionRaison) -> Dict[str, Any]:
    """Termine le sous-graphe en conservant la raison affinée."""
    return {"action": "conserver"}


async def supprimer_raison(state: StateConceptionRaison) -> Dict[str, Any]:
    """Termine le sous-graphe en ordonnant la suppression de la raison."""
    return {
        "action": "supprimer",
        "motif_suppression": state["verification"].motif_suppression,
    }


conception_raison_mise_en_demeure = (
    StateGraph(StateConceptionRaison)
    .add_node(redige_raison)
    .add_node(verifie_raison)
    .add_node(conserver_raison)
    .add_node(supprimer_raison)
    .add_edge("__start__", "redige_raison")
    .add_edge("redige_raison", "verifie_raison")
    .add_conditional_edges(
        "verifie_raison",
        route_apres_verification_raison,
        ["redige_raison", "conserver_raison", "supprimer_raison"],
    )
    .add_edge("conserver_raison", END)
    .add_edge("supprimer_raison", END)
    .compile(name="ConceptionRaisonMiseEnDemeure")
)
