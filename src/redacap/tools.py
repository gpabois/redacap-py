import os
import time
from dataclasses import dataclass
from datetime import date
from typing import Literal

import requests
from langchain.tools import tool

from redacap import reporter

LEGIFRANCE_TOKEN_URL = "https://oauth.piste.gouv.fr/api/oauth/token"
LEGIFRANCE_BASE_URL = os.environ["LEGIFRANCE_BASE_URL"].rstrip("/")
LEGIFRANCE_CLIENT_ID = os.environ["LEGIFRANCE_CLIENT_ID"]
LEGIFRANCE_CLIENT_SECRET = os.environ["LEGIFRANCE_CLIENT_SECRET"]

Fond = Literal[
    "JORF",
    "CNIL",
    "CETAT",
    "JURI",
    "JUFI",
    "CONSTIT",
    "KALI",
    "CODE_DATE",
    "CODE_ETAT",
    "LODA_DATE",
    "LODA_ETAT",
    "ALL",
    "CIRC",
    "ACCO",
]


@dataclass
class _Jeton:
    access_token: str = ""
    expire_à: float = 0.0

    @property
    def valide(self) -> bool:
        return bool(self.access_token) and time.time() < self.expire_à


_jeton = _Jeton()


def _jeton_valide() -> str:
    if not _jeton.valide:
        réponse = requests.post(
            LEGIFRANCE_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": LEGIFRANCE_CLIENT_ID,
                "client_secret": LEGIFRANCE_CLIENT_SECRET,
                "scope": "openid",
            },
        )
        réponse.raise_for_status()
        données = réponse.json()
        _jeton.access_token = données["access_token"]
        _jeton.expire_à = time.time() + données["expires_in"]
    return _jeton.access_token


def _appel_legifrance(route: str, payload: dict) -> dict:
    réponse = requests.post(
        f"{LEGIFRANCE_BASE_URL}/{route}",
        json=payload,
        headers={
            "Authorization": f"Bearer {_jeton_valide()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    réponse.raise_for_status()
    return réponse.json()


@tool
def recherche_fonds(query: str, fond: Fond = "ALL", page_size: int = 10) -> list[dict]:
    """Recherche des textes juridiques dans les fonds Légifrance (LODA, CODE, JURI, KALI, ...)."""
    payload = {
        "fond": fond,
        "recherche": {
            "champs": [
                {
                    "typeChamp": "ALL",
                    "operateur": "ET",
                    "criteres": [
                        {"valeur": query, "operateur": "ET", "typeRecherche": "UN_DES_MOTS"}
                    ],
                }
            ],
            "operateur": "ET",
            "pageNumber": 1,
            "pageSize": page_size,
            "sort": "PERTINENCE",
            "typePagination": "DEFAUT",
        },
    }
    résultats = _appel_legifrance("search", payload).get("results", [])
    reporter.détail(f"recherche_fonds({query!r}, fond={fond}) → {len(résultats)} résultat(s)")
    return résultats


def _fond_depuis_id(id: str) -> Fond:
    if id.startswith("LEGIARTI"):
        return "CODE_ETAT"
    if id.startswith("LEGITEXT"):
        return "LODA_ETAT"
    if id.startswith(("JURITEXT", "CETATEXT", "JUFITEXT")):
        return "JURI"
    if id.startswith("KALI"):
        return "KALI"
    raise ValueError(f"Impossible de déterminer le fond de contenu à partir de l'identifiant {id!r}")


@tool("recupere_contenu")
def récupère_contenu(id: str, fond: Fond) -> dict:
    """Récupère le contenu intégral d'un texte juridique Légifrance à partir de son identifiant et de son fond."""
    if fond not in ("CODE_DATE", "CODE_ETAT", "LODA_DATE", "LODA_ETAT", "JURI", "KALI"):
        fond = _fond_depuis_id(id)
    if fond in ("CODE_DATE", "CODE_ETAT"):
        contenu = _appel_legifrance("consult/getArticle", {"id": id})["article"]
    elif fond in ("LODA_DATE", "LODA_ETAT"):
        contenu = _appel_legifrance("consult/lawDecree", {"textId": id, "date": date.today().isoformat()})
    elif fond == "JURI":
        contenu = _appel_legifrance("consult/juri", {"textId": id, "searchedString": ""})["text"]
    elif fond == "KALI":
        contenu = _appel_legifrance("consult/kaliText", {"id": id, "searchedString": ""})
    else:
        raise ValueError(f"Récupération de contenu non supportée pour le fond {fond}")
    reporter.détail(f"recupere_contenu({id!r}, fond={fond})")
    return contenu


GEORISQUES_API_KEY = os.environ["GEORISQUES_API_KEY"]
GEORISQUES_ICPE_URL = "https://www.georisques.gouv.fr/api/v2/installations_classees"


@tool
def recherche_icpe_georisques(
    raison_sociale: str | None = None,
    codes_aiot: list[str] | None = None,
    siret: list[str] | None = None,
    departement: str | None = None,
    region: str | None = None,
    page_size: int = 10,
) -> list[dict]:
    """Recherche des installations classées pour la protection de l'environnement (ICPE) sur Géorisques."""
    params = {
        "raisonSociale": raison_sociale,
        "codesAiot": codes_aiot,
        "siret": siret,
        "departement": departement,
        "region": region,
        "pageSize": page_size,
    }
    params = {key: value for key, value in params.items() if value is not None}
    response = requests.get(
        GEORISQUES_ICPE_URL,
        params=params,
        headers={"Authorization": f"Bearer {GEORISQUES_API_KEY}"},
    )
    response.raise_for_status()
    résultats = response.json()["content"]
    critères = ", ".join(
        f"{clé}={valeur!r}"
        for clé, valeur in {
            "raison_sociale": raison_sociale,
            "codes_aiot": codes_aiot,
            "siret": siret,
            "departement": departement,
            "region": region,
        }.items()
        if valeur is not None
    )
    reporter.détail(f"recherche_icpe_georisques({critères}) → {len(résultats)} résultat(s)")
    return résultats
