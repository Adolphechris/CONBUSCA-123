"""
commandes/inputs.py

Dataclasses d'entrée pour les services du module commandes.
Construits depuis les forms Django validés — jamais depuis des données brutes.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class CommandeCreateInput:
    date_commande: date
    fournisseur_id: int | None = None
    taux: Decimal = Decimal('1.0000')
    devise_id: int | None = None


@dataclass(frozen=True)
class ArticleCommandeAddInput:
    commande_id: int
    article_id: int
    qte: int
    prix: Decimal


@dataclass(frozen=True)
class ArticleCommandeUpdateInput:
    detail_id: int
    qte: int
    prix: Decimal


@dataclass(frozen=True)
class CommandeUpdateInput:
    commande_id: int
    date_commande: date
    fournisseur_id: int | None = None
    taux: Decimal = Decimal('1.0000')
    devise_id: int | None = None
