"""Domain model for an Arrêté Préfectoral (French prefectural legal act)."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from redacap.icpe.report import Etablissement, RubriqueICPE


class TypeActe(str, Enum):
    """Nature de l'arrêté préfectoral."""

    AUTORISATION_EXPLOITER = "autorisation_exploiter"
    ENREGISTREMENT = "enregistrement"
    PRESCRIPTIONS_COMPLEMENTAIRES = "prescriptions_complementaires"
    MISE_EN_DEMEURE = "mise_en_demeure"
    SUSPENSION = "suspension"
    CONSIGNATION = "consignation"
    SANCTION_ADMINISTRATIVE = "sanction_administrative"
    ABROGATION = "abrogation"
    MODIFICATION = "modification"
    CESSATION_ACTIVITE = "cessation_activite"


class Article(BaseModel):
    """Une disposition (article) de l'arrêté."""

    numero: str = Field(..., description="Numéro de l'article, ex. 'Article 1'")
    titre: Optional[str] = None
    contenu: str


class LegalAct(BaseModel):
    """Arrêté préfectoral."""

    numero: Optional[str] = Field(
        None, description="Numéro de l'arrêté, attribué à la signature"
    )
    type_acte: TypeActe
    date_signature: Optional[date] = Field(
        None, description="Date de signature, inconnue tant que l'arrêté est en projet"
    )
    date_notification: Optional[date] = None
    prefecture: Optional[str] = None
    departement: Optional[str] = None
    dreal: Optional[str] = Field(
        None,
        description="Direction régionale (DREAL/DEAL) instructrice, affichée dans le timbre administratif",
    )
    signataire: Optional[str] = Field(
        None, description="Nom et qualité du signataire (préfet ou délégataire)"
    )
    etablissement: Optional[Etablissement] = None
    titre: Optional[str] = Field(
        None, description="Titre bref de l'arrêté, identifiant l'acte et l'exploitant concerné"
    )
    objet: str = Field(..., description="Objet de l'arrêté")
    visas: List[str] = Field(
        default_factory=list, description="Textes réglementaires et documents visés"
    )
    considerants: List[str] = Field(
        default_factory=list, description="Motifs justifiant l'arrêté"
    )
    articles: List[Article] = Field(default_factory=list)
    rubriques: List[RubriqueICPE] = Field(
        default_factory=list, description="Rubriques ICPE couvertes par l'arrêté"
    )
    arretes_modifies: List[str] = Field(
        default_factory=list,
        description="Références des arrêtés antérieurs modifiés ou abrogés par cet arrêté",
    )
    delai_execution: Optional[date] = Field(
        None, description="Délai imparti à l'exploitant pour se conformer"
    )
    date_entree_vigueur: Optional[date] = None
    voies_recours: Optional[str] = Field(
        None, description="Voies et délais de recours mentionnés dans l'arrêté"
    )
