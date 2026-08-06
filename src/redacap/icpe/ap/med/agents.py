"""Reusable LLM agent abstraction and the extraction agents built on it.

Each agent pairs a chat model with a system prompt loaded from a sibling
markdown file in the `agents/` directory, and constrains its output to a
Pydantic schema via structured output.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Type, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, model_validator

from redacap.icpe.ap.legal_act import Article
from redacap.icpe.report import InspectionReport
from redacap.model import model

PROMPTS_DIR = Path(__file__).parent / "agents"


@dataclass
class Agent:
    """A chat model bound to a prompt template and a structured output schema."""

    model: BaseChatModel
    prompt_name: str
    output_schema: Type[BaseModel]

    @property
    def system_prompt(self) -> str:
        return (PROMPTS_DIR / f"{self.prompt_name}.md").read_text(encoding="utf-8")

    async def ainvoke(self, user_input: str) -> BaseModel:
        structured_model = self.model.with_structured_output(self.output_schema)
        messages = [SystemMessage(self.system_prompt), HumanMessage(user_input)]
        return await structured_model.ainvoke(messages)


class RaisonMiseEnDemeure(BaseModel):
    constat: str
    constat_numero: Optional[int] = Field(
        None,
        description=(
            "Numéro (1-based) du constat correspondant dans la liste des constats "
            "numérotés de la synthèse structurée du rapport, si un constat structuré "
            "correspond précisément à cette raison"
        ),
    )
    synthèse: str
    reference_article: str
    reference_source: str
    disposition: str
    action: Optional[str]
    delai_valeur: int
    délai_unité: str


class RaisonsMiseEnDemeure(BaseModel):
    """Liste des raisons justifiant une mise en demeure, issues d'un rapport d'inspection."""

    raisons: List[RaisonMiseEnDemeure] = Field(default_factory=list)


analyse_mise_en_demeure = Agent(
    model=model,
    prompt_name="analyse_mise_en_demeure",
    output_schema=RaisonsMiseEnDemeure,
)


class ResultatVerificationUnitaire(BaseModel):
    """Analyse et verdict d'un point de contrôle unitaire."""

    analyse: str = Field(
        ..., description="Ce qui a été vérifié et ce qui est constaté pour ce point précis"
    )
    conforme: bool = Field(..., description="True si ce point précis est conforme")


class VerificationDetaillee(BaseModel):
    """Détail, point par point, du contrôle d'un contenu rédigé par un agent de rédaction.

    La conformité globale n'est pas demandée au modèle : elle est calculée par
    le nœud vérificateur à partir des verdicts unitaires (un ``all()``), pour
    éviter qu'un commentaire de complaisance sur un point conforme ne pollue
    un champ de synthèse censé ne contenir que des anomalies.
    """

    resultats: List[ResultatVerificationUnitaire] = Field(default_factory=list)


class DecisionRaison(str, Enum):
    """Décision rendue par le vérificateur d'une raison de mise en demeure."""

    CONFORME = "conforme"
    A_CORRIGER = "a_corriger"
    A_SUPPRIMER = "a_supprimer"


class VerificationRaison(BaseModel):
    """Résultat du contrôle d'une raison de mise en demeure."""

    decision: DecisionRaison
    anomalies: List[str] = Field(
        default_factory=list,
        description="Corrections à apporter, renseigné si decision='a_corriger'",
    )
    motif_suppression: Optional[str] = Field(
        None,
        description="Motif justifiant la suppression, renseigné si decision='a_supprimer'",
    )

    @model_validator(mode="after")
    def _nettoyer_champs_selon_decision(self) -> "VerificationRaison":
        """Ignore anomalies/motif_suppression non pertinents au regard de la décision.

        Certains modèles commentent chaque champ vérifié (y compris ceux qui
        sont conformes) malgré les consignes du prompt ; on neutralise ce bruit
        ici plutôt que de compter sur la seule discipline du prompt.
        """
        if self.decision != DecisionRaison.A_CORRIGER:
            self.anomalies = []
        if self.decision != DecisionRaison.A_SUPPRIMER:
            self.motif_suppression = None
        return self


redaction_raison_mise_en_demeure = Agent(
    model=model,
    prompt_name="redaction_raison_mise_en_demeure",
    output_schema=RaisonMiseEnDemeure,
)

verificateur_raison_mise_en_demeure = Agent(
    model=model,
    prompt_name="verificateur_raison_mise_en_demeure",
    output_schema=VerificationRaison,
)

structuration_rapport_inspection = Agent(
    model=model,
    prompt_name="structuration_rapport_inspection",
    output_schema=InspectionReport,
)


class Titre(BaseModel):
    """Titre de l'arrêté de mise en demeure."""

    titre: str = Field(..., description="Titre bref de l'arrêté")


class Visas(BaseModel):
    """Liste des visas (« Vu ... ») de l'arrêté de mise en demeure."""

    visas: List[str] = Field(default_factory=list)


class Considerants(BaseModel):
    """Liste des considérants motivant l'arrêté de mise en demeure."""

    considerants: List[str] = Field(default_factory=list)


class ArticlesSuivants(BaseModel):
    """Articles complémentaires de l'arrêté (voie de recours, notification...)."""

    articles: List[Article] = Field(default_factory=list)


redaction_titre = Agent(
    model=model,
    prompt_name="redaction_titre",
    output_schema=Titre,
)

redaction_visas = Agent(
    model=model,
    prompt_name="redaction_visas",
    output_schema=Visas,
)

redaction_considerants = Agent(
    model=model,
    prompt_name="redaction_considerants",
    output_schema=Considerants,
)

redaction_article_premier = Agent(
    model=model,
    prompt_name="redaction_article_premier",
    output_schema=Article,
)

redaction_articles_suivants = Agent(
    model=model,
    prompt_name="redaction_articles_suivants",
    output_schema=ArticlesSuivants,
)


verificateur_titre = Agent(
    model=model,
    prompt_name="verificateur_titre",
    output_schema=VerificationDetaillee,
)

verificateur_visas = Agent(
    model=model,
    prompt_name="verificateur_visas",
    output_schema=VerificationDetaillee,
)

verificateur_considerants = Agent(
    model=model,
    prompt_name="verificateur_considerants",
    output_schema=VerificationDetaillee,
)

verificateur_article_premier = Agent(
    model=model,
    prompt_name="verificateur_article_premier",
    output_schema=VerificationDetaillee,
)

verificateur_articles_suivants = Agent(
    model=model,
    prompt_name="verificateur_articles_suivants",
    output_schema=VerificationDetaillee,
)
