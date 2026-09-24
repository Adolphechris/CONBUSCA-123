"""
commandes/services.py

Toute la logique métier du module commandes.
Chaque service = une action nommée par un verbe.
Chaque service qui écrit en DB est @transaction.atomic.

Workflow des commandes :
  BROUILLON → VALIDEE → TRANSFORMEE (en approvisionnement)
"""

from dataclasses import dataclass

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.core.exceptions import ValidationError

from users.models import CustomUser

from approvisionnements.models import Approvisionnement, DetailsApprovisionnement
from approvisionnements.services import ApprovisionnementService

from .exceptions import CommandeDejaClotureError, CommandeNonValideeError
from .inputs import (
    ArticleCommandeAddInput,
    ArticleCommandeUpdateInput,
    CommandeCreateInput,
    CommandeUpdateInput,
)
from .models import Commande, DetailsCommande


# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class CommandeResult:
    commande: Commande


@dataclass
class DetailCommandeResult:
    detail: DetailsCommande
    merged: bool  # True si l'article existait déjà et la quantité a été fusionnée


# ── Helpers privés ────────────────────────────────────────────────────────────

def _generate_numero() -> int:
    """
    Génère le prochain numéro de commande, sans risque de race condition.
    Format initial : YY0001 (ex: 260001 pour 2026).
    Ensuite : dernier numéro + 1.
    select_for_update() pose un verrou sur les lignes lues — appelé
    uniquement depuis un service @transaction.atomic.
    """
    last_num = (
        Commande.objects
        .select_for_update()
        .aggregate(Max('numero'))['numero__max']
    )
    if last_num is None:
        year_suffix = str(timezone.now().year)[2:]
        return int(year_suffix + '0001')
    return last_num + 1


# ── Services ──────────────────────────────────────────────────────────────────

@transaction.atomic
def creer_commande(
    *,
    data: CommandeCreateInput,
    current_user: CustomUser,
) -> CommandeResult:
    commande = Commande.objects.create(
        numero=_generate_numero(),
        date_commande=data.date_commande,
        fournisseur_id=data.fournisseur_id,
        devise_id=data.devise_id,
        taux=data.taux,
        cree_par=current_user,
    )
    return CommandeResult(commande=commande)


@transaction.atomic
def modifier_commande(
    *,
    data: CommandeUpdateInput,
    current_user: CustomUser,
) -> CommandeResult:
    commande = Commande.objects.select_for_update().get(id=data.commande_id)
    if not commande.est_modifiable and not current_user.is_superuser:
        raise ValidationError("Une commande validée par la Direction ne peut plus être modifiée.")
    commande.date_commande = data.date_commande
    commande.fournisseur_id = data.fournisseur_id
    commande.devise_id = data.devise_id
    commande.taux = data.taux
    commande.modifie_par = current_user
    commande.save(update_fields=[
        'date_commande', 'fournisseur', 'devise', 'taux',
        'modifie_par', 'date_modification',
    ])
    return CommandeResult(commande=commande)


@transaction.atomic
def soumettre_commande(
    *,
    commande_id: int,
    current_user: CustomUser,
) -> Commande:
    """Soumet une commande en brouillon à l'arbitrage du Super-Administrateur."""
    from notifications.models import NotificationInterne
    commande = Commande.objects.select_for_update().get(id=commande_id)
    if not commande.detailscommande_set.exists():
        raise ValidationError("Une commande sans articles ne peut pas être soumise.")
    commande.statut = Commande.EN_ATTENTE
    commande.modifie_par = current_user
    commande.save(update_fields=['statut', 'modifie_par', 'date_modification'])

    NotificationInterne.notifier_superadmins(
        titre=f"Proposition de commande N° {commande.numero}",
        message=f"{current_user.username} a soumis une proposition de commande pour validation.",
        type_notification=NotificationInterne.INFO,
        lien=reverse('direction_cockpit') if 'direction_cockpit' else reverse('commande_details', args=[commande.pk]),
        emetteur=current_user,
    )
    return commande


@transaction.atomic
def valider_commande(
    *,
    commande_id: int,
    current_user: CustomUser,
    commentaire: str = "",
) -> Commande:
    """
    Valide une commande par la Direction (EN_ATTENTE ou BROUILLON → VALIDEE).
    Verrouille la commande et notifie l'émetteur.
    """
    from notifications.models import NotificationInterne
    commande = Commande.objects.select_for_update().get(id=commande_id)
    
    if commande.statut not in (Commande.BROUILLON, Commande.EN_ATTENTE):
        raise ValidationError(
            f"La commande {commande.numero} ne peut pas être validée (statut actuel: {commande.get_statut_display()})."
        )
    
    if not commande.actif:
        raise CommandeDejaClotureError(
            f"La commande {commande.numero} est désactivée."
        )
    
    if not commande.detailscommande_set.exists():
        raise ValidationError(
            "Une commande sans articles ne peut pas être validée."
        )
    
    commande.statut = Commande.VALIDEE
    commande.valide_par = current_user
    commande.date_validation = timezone.now()
    if commentaire:
        commande.commentaire_decision = commentaire
    commande.modifie_par = current_user
    commande.save(update_fields=[
        'statut', 'valide_par', 'date_validation', 'commentaire_decision',
        'modifie_par', 'date_modification',
    ])

    # Notification in-app au créateur de la commande
    NotificationInterne.notifier(
        destinataire=commande.cree_par,
        titre=f"Commande N° {commande.numero} validée",
        message=f"La Direction a validé votre commande N° {commande.numero}. Vous pouvez désormais générer et imprimer le bon de commande.",
        type_notification=NotificationInterne.VALIDATION,
        lien=reverse('commande_details', args=[commande.pk]),
        emetteur=current_user,
    )
    
    return commande


@transaction.atomic
def refuser_commande(
    *,
    commande_id: int,
    current_user: CustomUser,
    motif_refus: str,
) -> Commande:
    """
    Refuse une proposition de commande par la Direction avec motif obligatoire.
    """
    from notifications.models import NotificationInterne
    if not motif_refus or not motif_refus.strip():
        raise ValidationError("Le motif du refus est obligatoire.")

    commande = Commande.objects.select_for_update().get(id=commande_id)
    commande.statut = Commande.REFUSEE
    commande.valide_par = current_user
    commande.date_validation = timezone.now()
    commande.commentaire_decision = motif_refus.strip()
    commande.modifie_par = current_user
    commande.save(update_fields=[
        'statut', 'valide_par', 'date_validation', 'commentaire_decision',
        'modifie_par', 'date_modification',
    ])

    NotificationInterne.notifier(
        destinataire=commande.cree_par,
        titre=f"Commande N° {commande.numero} refusée",
        message=f"Votre commande N° {commande.numero} a été refusée par la Direction. Motif : {motif_refus.strip()}",
        type_notification=NotificationInterne.REFUS,
        lien=reverse('commande_details', args=[commande.pk]),
        emetteur=current_user,
    )

    return commande


@transaction.atomic
def transformer_commande(
    *,
    commande_id: int,
    current_user: CustomUser,
) -> Approvisionnement:
    """
    Transforme une commande validée en approvisionnement (VALIDEE → TRANSFORMEE).
    
    Règles :
    - La commande doit être VALIDEE
    - Crée un Approvisionnement avec les mêmes lignes
    - Marque la commande comme TRANSFORMEE
    """
    commande = Commande.objects.select_for_update().get(id=commande_id)
    
    if commande.statut != Commande.VALIDEE:
        raise ValidationError(
            f"La commande {commande.numero} doit être validée avant transformation (statut: {commande.statut})."
        )
    
    if not commande.actif:
        raise CommandeDejaClotureError(
            f"La commande {commande.numero} est déjà clôturée."
        )
    
    # Créer l'approvisionnement
    from approvisionnements.inputs import ApprovisionnementCreateInput
    
    approv_input = ApprovisionnementCreateInput(
        fournisseur_id=commande.fournisseur_id,
        devise_id=commande.devise_id,
        taux=commande.taux,
    )
    
    approv_result = ApprovisionnementService.creer_approvisionnement(
        data=approv_input,
        current_user=current_user,
    )
    
    # Ajouter les lignes de commande à l'approvisionnement
    for detail in commande.detailscommande_set.all():
        ligne_input = DetailsApprovisionnementCreateInput(
            approvisionnement_id=approv_result.approvisionnement.pk,
            article_id=detail.article_id,
            qte=detail.qte,
            prix_achat=detail.prix,
        )
        ApprovisionnementService.ajouter_ligne_approvisionnement(
            data=ligne_input,
            current_user=current_user,
        )
    
    # Marquer la commande comme transformée
    commande.statut = Commande.TRANSFORMEE
    commande.modifie_par = current_user
    commande.save(update_fields=['statut', 'modifie_par', 'date_modification'])
    
    return approv_result.approvisionnement


@transaction.atomic
def cloturer_commande(
    *,
    commande_id: int,
    current_user: CustomUser,
) -> Commande:
    commande = Commande.objects.select_for_update().get(id=commande_id)
    if not commande.actif:
        raise CommandeDejaClotureError(
            f"La commande {commande.numero} est déjà clôturée."
        )
    commande.actif = False
    commande.modifie_par = current_user
    commande.save(update_fields=['actif', 'modifie_par', 'date_modification'])
    return commande


def calculer_besoins_reapprovisionnement():
    """
    Calcule l'ensemble des articles à réapprovisionner (rupture, sous-seuil, sous-15j).
    Retourne la liste des suggestions prêtes pour affichage ou génération de commande.
    """
    from decimal import Decimal
    import datetime
    from django.db.models import Sum
    from produits.models import Stock as StockModel, MouvementStock, Article
    from collections import defaultdict

    today = timezone.now().date()
    debut_30j = today - datetime.timedelta(days=29)

    stock_actuel = {
        row['article_id']: row['qte']
        for row in StockModel.objects.values('article_id').annotate(qte=Sum('qte'))
    }

    ecoulement_30j = defaultdict(int)
    for row in (MouvementStock.objects
                .filter(type=MouvementStock.OUT,
                        date_creation__date__range=(debut_30j, today))
                .values('article_id')
                .annotate(total=Sum('qte'))):
        ecoulement_30j[row['article_id']] = row['total']

    article_ids = set(stock_actuel.keys()) | set(ecoulement_30j.keys())
    articles = {
        a.pk: a
        for a in Article.objects.filter(pk__in=article_ids, actif=True).select_related('fournisseur', 'unite')
    }

    rows = []
    for aid in article_ids:
        a = articles.get(aid)
        if not a:
            continue
        qte_stock = stock_actuel.get(aid, 0)
        ecoul = ecoulement_30j.get(aid, 0)
        ecoul_par_jour = round(ecoul / 30, 2)
        seuil = a.seuil or 0

        jours_restants = round(qte_stock / ecoul_par_jour, 1) if ecoul_par_jour > 0 else None

        en_rupture = qte_stock == 0
        sous_seuil = qte_stock <= seuil
        sous_15j = jours_restants is not None and jours_restants < 15

        if not (en_rupture or sous_seuil or sous_15j):
            continue

        if en_rupture:
            urgence = 'rupture'
        elif sous_seuil or (jours_restants is not None and jours_restants <= 5):
            urgence = 'critique'
        else:
            urgence = 'alerte'

        if ecoul_par_jour > 0:
            qte_suggere = max(0, round(ecoul_par_jour * 30 - qte_stock))
        else:
            qte_suggere = max(0, seuil - qte_stock)

        if qte_suggere <= 0:
            qte_suggere = max(1, seuil if seuil > 0 else 5)

        prix_achat = Decimal(str(a.prix_achat or 0))

        rows.append({
            'article': a,
            'article_id': a.pk,
            'designation': a.designation,
            'fournisseur': str(a.fournisseur) if a.fournisseur else 'Non assigné',
            'fournisseur_obj': a.fournisseur,
            'unite': str(a.unite) if a.unite else '—',
            'stock_actuel': qte_stock,
            'seuil': seuil,
            'ecoul_30j': ecoul,
            'ecoul_par_jour': ecoul_par_jour,
            'jours_restants': jours_restants,
            'qte_suggere': int(qte_suggere),
            'prix_achat': prix_achat,
            'total_estime': round(prix_achat * Decimal(str(qte_suggere)), 2),
            'urgence': urgence,
        })

    def sort_key(r):
        order = {'rupture': 0, 'critique': 1, 'alerte': 2}
        jr = r['jours_restants'] if r['jours_restants'] is not None else 9999
        return (order[r['urgence']], jr)

    rows.sort(key=sort_key)
    return rows


@transaction.atomic
def generer_commande_automatique(*, current_user: CustomUser) -> Commande:
    """
    Génère une proposition de commande groupée automatique (multi-fournisseurs)
    à partir des besoins calculés, soumise obligatoirement au statut EN_ATTENTE.
    """
    from notifications.models import NotificationInterne
    besoins = calculer_besoins_reapprovisionnement()
    if not besoins:
        raise ValidationError("Aucun article ne nécessite de réapprovisionnement actuellement.")

    commande = Commande.objects.create(
        numero=_generate_numero(),
        date_commande=timezone.now().date(),
        fournisseur=None,  # Commande interne multi-fournisseurs
        statut=Commande.EN_ATTENTE,
        cree_par=current_user,
        commentaire_decision="Générée automatiquement par le système d'analyse des stocks",
    )

    details = []
    for b in besoins:
        details.append(DetailsCommande(
            commande=commande,
            article_id=b['article_id'],
            qte=b['qte_suggere'],
            prix=b['prix_achat'],
        ))
    DetailsCommande.objects.bulk_create(details)

    NotificationInterne.notifier_superadmins(
        titre=f"Proposition de commande auto N° {commande.numero}",
        message=f"{current_user.username} a généré une commande automatique de réapprovisionnement ({len(details)} articles) soumise pour validation.",
        type_notification=NotificationInterne.INFO,
        lien=reverse('direction_cockpit') if 'direction_cockpit' else reverse('commande_details', args=[commande.pk]),
        emetteur=current_user,
    )

    return commande


@transaction.atomic
def annuler_commande(
    *,
    commande_id: int,
    current_user: CustomUser,
) -> None:
    """
    Suppression physique — exception explicite à la règle logique du projet.
    Les commandes sont supprimées pour ne pas polluer l'historique.
    Les DetailsCommande en cascade (FK PROTECT → supprimés manuellement d'abord).
    """
    commande = Commande.objects.select_for_update().get(id=commande_id)
    if not commande.est_modifiable and not current_user.is_superuser:
        raise ValidationError("Une commande validée par la Direction ne peut être annulée que par un administrateur.")
    commande.detailscommande_set.all().delete()
    commande.delete()


@transaction.atomic
def ajouter_article_commande(
    *,
    data: ArticleCommandeAddInput,
    current_user: CustomUser,
) -> DetailCommandeResult:
    """
    Ajoute un article à une commande.
    Si l'article est déjà présent, fusionne la quantité (pas de doublon).
    """
    commande = Commande.objects.select_for_update().get(id=data.commande_id)
    if not commande.est_modifiable and not current_user.is_superuser:
        raise ValidationError("Impossible d'ajouter des articles à une commande validée ou clôturée.")

    existing = (
        DetailsCommande.objects
        .filter(commande=commande, article_id=data.article_id)
        .first()
    )

    if existing:
        existing.qte += data.qte
        existing.save(update_fields=['qte', 'date_modification'])
        return DetailCommandeResult(detail=existing, merged=True)

    detail = DetailsCommande.objects.create(
        commande=commande,
        article_id=data.article_id,
        qte=data.qte,
        prix=data.prix,
    )
    return DetailCommandeResult(detail=detail, merged=False)


@transaction.atomic
def modifier_article_commande(
    *,
    data: ArticleCommandeUpdateInput,
    current_user: CustomUser,
) -> DetailsCommande:
    detail = DetailsCommande.objects.select_for_update().get(id=data.detail_id)
    if not detail.commande.est_modifiable and not current_user.is_superuser:
        raise ValidationError("Impossible de modifier une ligne d'une commande validée ou clôturée.")
    detail.qte = data.qte
    detail.prix = data.prix
    detail.save(update_fields=['qte', 'prix', 'date_modification'])
    return detail


@transaction.atomic
def supprimer_article_commande(
    *,
    detail_id: int,
    current_user: CustomUser,
) -> None:
    """
    Suppression physique d'une ligne — DetailsCommande n'a pas de champ actif.
    Seule la Commande elle-même est soumise à la règle de suppression logique.
    """
    detail = DetailsCommande.objects.select_for_update().get(id=detail_id)
    if not detail.commande.est_modifiable and not current_user.is_superuser:
        raise ValidationError("Impossible de supprimer une ligne d'une commande validée ou clôturée.")
    detail.delete()
