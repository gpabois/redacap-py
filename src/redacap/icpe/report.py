"""Domain model for a Rapport d'inspection ICPE (French classified-installation inspection report)."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class RegimeICPE(str, Enum):
    """Régime de classement ICPE de l'installation ou d'une rubrique."""

    DECLARATION = "declaration"
    ENREGISTREMENT = "enregistrement"
    AUTORISATION = "autorisation"
    AUTORISATION_SEVESO_SEUIL_BAS = "autorisation_seveso_seuil_bas"
    AUTORISATION_SEVESO_SEUIL_HAUT = "autorisation_seveso_seuil_haut"


class TypeInspection(str, Enum):
    """Nature de la visite d'inspection."""

    PROGRAMMEE = "programmee"
    INOPINEE = "inopinee"
    SUITE_A_PLAINTE = "suite_a_plainte"
    SUITE_A_INCIDENT = "suite_a_incident"
    SUITE_A_MISE_EN_DEMEURE = "suite_a_mise_en_demeure"


class NiveauConformite(str, Enum):
    """Niveau de conformité constaté pour un point de contrôle."""

    CONFORME = "conforme"
    NON_CONFORME = "non_conforme"
    NON_APPLICABLE = "non_applicable"
    NON_VERIFIABLE = "non_verifiable"


class TypeManquement(str, Enum):
    """Qualification juridique du manquement relevé par un constat, le cas échéant."""

    INOBSERVATION = "inobservation"
    IRREGULARITE_ADMINISTRATIVE = "irregularite_administrative"
    AUCUN = "aucun"


class SuiteAdministrative(str, Enum):
    """Suite proposée par l'inspecteur à l'issue du contrôle."""

    AUCUNE = "aucune"
    OBSERVATIONS = "observations"
    MISE_EN_DEMEURE = "mise_en_demeure"
    CONSIGNATION = "consignation"
    AMENDE_ADMINISTRATIVE = "amende_administrative"
    ASTREINTE_JOURNALIERE = "astreinte_journaliere"
    SUSPENSION = "suspension"
    PROCES_VERBAL = "proces_verbal"


class RubriqueICPE(BaseModel):
    """Une rubrique de la nomenclature ICPE concernée par l'établissement."""

    numero: str = Field(..., description="Numéro de rubrique, ex. '2560'")
    libelle: str = Field(..., description="Libellé de la rubrique")
    regime: RegimeICPE
    volume_autorise: Optional[str] = Field(
        None, description="Volume, capacité ou seuil autorisé pour cette rubrique"
    )


class Etablissement(BaseModel):
    """Identification de l'établissement inspecté."""

    raison_sociale: str
    siret: Optional[str] = None
    exploitant: Optional[str] = Field(
        None, description="Nom de l'exploitant si différent de la raison sociale"
    )
    adresse: str
    commune: str
    code_postal: str
    regime_global: RegimeICPE
    rubriques: List[RubriqueICPE] = Field(default_factory=list)
    reference_arrete_autorisation: Optional[str] = None

class PointDeControle(BaseModel):
    """Un point de contrôle constaté lors de l'inspection."""
    numero: int
    thematique: str = Field(
        ...,
        description="Thème inspecté, ex. 'Déchets', 'Rejets aqueux', 'Risques accidentels'",
    )
    reference_reglementaire: Optional[str] = Field(
        None, description="Article ou prescription réglementaire concernée"
    )
    constats: list[Constat]

class Constat(BaseModel):
    """Un constat unitaire dans un point de contrôle"""

    thematique: str = Field(
        ...,
        description="Thème inspecté, ex. 'Déchets', 'Rejets aqueux', 'Risques accidentels'",
    )
    description: str
    conformite: NiveauConformite
    type_manquement: TypeManquement = Field(
        ...,
        description=(
            "Qualification du manquement relevé : inobservation d'une prescription "
            "technique, irrégularité administrative, ou aucun des deux"
        ),
    )
    constats: list[Constat]
    suites: Optional[SuiteAdministrative]
    delai_mise_en_conformite: Optional[str] = None

class InspectionReport(BaseModel):
    """Rapport d'inspection ICPE."""

    reference: Optional[str] = Field(None, description="Numéro ou référence du rapport")
    etablissement: Etablissement
    date_inspection: date
    type_inspection: TypeInspection
    inspecteurs: List[str] = Field(default_factory=list)
    objet_inspection: Optional[str] = Field(
        None, description="Objectif ou thème principal de la visite"
    )
    contexte: Optional[str] = Field(
        None, description="Contexte et antécédents de l'établissement (contentieux, précédentes inspections)"
    )
    points_de_controle: List[PointDeControle] = Field(default_factory=list)
    suite_administrative: SuiteAdministrative = SuiteAdministrative.AUCUNE
    conclusion: Optional[str] = None
