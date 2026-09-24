"""
direction/views.py

Cockpit Direction — Interface exclusive du Super-Administrateur.
Toutes les actions de validation passent par ici.
Aucune logique métier : les services font le travail.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from caisse.models import CaisseCourante, DemandeDecaissement
from commandes.models import Commande
from notifications.models import NotificationInterne
from users.models import CustomUser


# ── Mixin Superadmin ──────────────────────────────────────────────────────────

class SuperAdminRequiredMixin(LoginRequiredMixin):
    """Réservé exclusivement au superutilisateur."""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_superuser:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


def is_htmx(request) -> bool:
    return request.headers.get("HX-Request", "").lower() == "true"


# ── Cockpit Principal ──────────────────────────────────────────────────────────

class DirectionCockpitView(SuperAdminRequiredMixin, TemplateView):
    """
    Vue principale du Super-Administrateur.
    Agrège en un seul écran :
      - Commandes EN_ATTENTE
      - Demandes de décaissement EN_ATTENTE
      - Résumé trésorerie (caisses ouvertes)
      - Notifications non lues
    """
    template_name = 'direction/cockpit.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # Commandes soumises à la Direction
        commandes_attente = (
            Commande.objects
            .filter(statut=Commande.EN_ATTENTE)
            .select_related('cree_par', 'fournisseur', 'devise')
            .order_by('-date_commande')
        )

        # Décaissements soumis à la Direction
        decaissements_attente = (
            DemandeDecaissement.objects
            .filter(statut=DemandeDecaissement.EN_ATTENTE)
            .select_related('caisse', 'demandeur', 'rubrique', 'sous_rubrique',
                            'fournisseur', 'client', 'creancier', 'agent')
            .order_by('-date_demande')
        )

        # Résumé trésorerie
        caisses_ouvertes = (
            CaisseCourante.objects
            .filter(est_ouverte=True)
            .select_related('caisse', 'ouvert_par')
        )

        # Notifications non lues
        notifs_non_lues = (
            NotificationInterne.objects
            .filter(destinataire=self.request.user, lu=False)
            .order_by('-date_creation')[:10]
        )

        # Statistiques rapides
        ctx.update({
            'commandes_attente': commandes_attente,
            'decaissements_attente': decaissements_attente,
            'caisses_ouvertes': caisses_ouvertes,
            'notifs_non_lues': notifs_non_lues,
            'nb_commandes_attente': commandes_attente.count(),
            'nb_decaissements_attente': decaissements_attente.count(),
            'total_caisses': sum(
                c.solde_theorique() if hasattr(c, 'solde_theorique') else 0
                for c in caisses_ouvertes
            ),
        })
        return ctx


# ── Actions sur les Commandes ─────────────────────────────────────────────────

class DirectionCommandeValiderView(SuperAdminRequiredMixin, View):
    """
    Valide une commande EN_ATTENTE.
    Délègue à commandes.services.valider_commande.
    next= dans POST pour rediriger vers le cockpit.
    """
    def post(self, request, pk):
        from commandes.services import valider_commande
        commande = get_object_or_404(Commande, pk=pk)
        commentaire = request.POST.get('commentaire', '').strip()
        try:
            valider_commande(
                commande_id=commande.pk,
                current_user=request.user,
                commentaire=commentaire,
            )
            messages.success(
                request,
                f"Commande N° {commande.numero} validée avec succès."
            )
        except Exception as e:
            messages.error(request, f"Erreur validation commande : {e}")

        next_url = request.POST.get('next') or reverse('direction_cockpit')
        if is_htmx(request):
            response = HttpResponse()
            response['HX-Redirect'] = next_url
            return response
        return redirect(next_url)


class DirectionCommandeRefuserView(SuperAdminRequiredMixin, View):
    """
    Refuse une commande EN_ATTENTE avec motif obligatoire.
    Délègue à commandes.services.refuser_commande.
    """
    def post(self, request, pk):
        from commandes.services import refuser_commande
        commande = get_object_or_404(Commande, pk=pk)
        motif = request.POST.get('motif_refus', '').strip()
        if not motif:
            motif = "Refusée par la Direction — aucun commentaire fourni"
        try:
            refuser_commande(
                commande_id=commande.pk,
                current_user=request.user,
                motif_refus=motif,
            )
            messages.warning(
                request,
                f"Commande N° {commande.numero} refusée."
            )
        except Exception as e:
            messages.error(request, f"Erreur refus commande : {e}")

        next_url = request.POST.get('next') or reverse('direction_cockpit')
        if is_htmx(request):
            response = HttpResponse()
            response['HX-Redirect'] = next_url
            return response
        return redirect(next_url)


# ── Actions sur les Décaissements ─────────────────────────────────────────────

class DirectionDecaissementApprouverView(SuperAdminRequiredMixin, View):
    """
    Approuve une demande de décaissement EN_ATTENTE.
    La Direction peut modifier le montant (montant_approuve).
    Le montant approuvé peut être différent du montant demandé.
    RÈGLE MÉDICO-LÉGALE : Aucun MouvementCaisse créé ici.
    C'est le caissier qui exécute après approbation.
    """
    @transaction.atomic
    def post(self, request, pk):
        demande = get_object_or_404(DemandeDecaissement, pk=pk)

        if demande.statut != DemandeDecaissement.EN_ATTENTE:
            messages.error(request, "Cette demande n'est plus en attente.")
            return redirect(request.POST.get('next') or reverse('direction_cockpit'))

        montant_str = request.POST.get('montant_approuve', '').strip()
        commentaire = request.POST.get('commentaire', '').strip()

        try:
            if montant_str:
                from decimal import Decimal
                montant_approuve = Decimal(montant_str.replace(',', '.'))
            else:
                montant_approuve = demande.montant  # Approuve le montant exact demandé
        except Exception:
            messages.error(request, "Montant invalide.")
            return redirect(request.POST.get('next') or reverse('direction_cockpit'))

        demande.statut = DemandeDecaissement.APPROUVEE
        demande.montant_approuve = montant_approuve
        demande.valide_par = request.user
        demande.date_decision = timezone.now()
        demande.commentaire_decision = commentaire or None
        demande.save(update_fields=[
            'statut', 'montant_approuve', 'valide_par',
            'date_decision', 'commentaire_decision'
        ])

        # Notification au caissier demandeur
        if demande.demandeur:
            NotificationInterne.notifier(
                destinataire=demande.demandeur,
                titre=f"Décaissement #{demande.pk} approuvé — {montant_approuve:,.0f} FC",
                message=(
                    f"Votre demande de décaissement de {demande.montant:,.0f} FC a été approuvée "
                    f"par {request.user.get_full_name() or request.user.username} "
                    f"pour un montant de {montant_approuve:,.0f} FC. "
                    f"Vous pouvez maintenant procéder à l'exécution."
                    + (f"\nCommentaire Direction : {commentaire}" if commentaire else "")
                ),
                type_notification=NotificationInterne.VALIDATION,
                emetteur=request.user,
                lien=reverse('caisse_details', args=[demande.caisse.caisse_id]),
            )

        messages.success(
            request,
            f"Décaissement #{demande.pk} approuvé — Montant : {montant_approuve:,.0f} FC"
        )
        next_url = request.POST.get('next') or reverse('direction_cockpit')
        if is_htmx(request):
            response = HttpResponse()
            response['HX-Redirect'] = next_url
            return response
        return redirect(next_url)


class DirectionDecaissementRefuserView(SuperAdminRequiredMixin, View):
    """
    Refuse une demande de décaissement EN_ATTENTE avec motif.
    """
    @transaction.atomic
    def post(self, request, pk):
        demande = get_object_or_404(DemandeDecaissement, pk=pk)

        if demande.statut != DemandeDecaissement.EN_ATTENTE:
            messages.error(request, "Cette demande n'est plus en attente.")
            return redirect(request.POST.get('next') or reverse('direction_cockpit'))

        motif = request.POST.get('motif_refus', '').strip()
        if not motif:
            motif = "Refusée par la Direction — aucun motif fourni"

        demande.statut = DemandeDecaissement.REFUSEE
        demande.valide_par = request.user
        demande.date_decision = timezone.now()
        demande.commentaire_decision = motif
        demande.save(update_fields=[
            'statut', 'valide_par', 'date_decision', 'commentaire_decision'
        ])

        # Notification au caissier demandeur
        if demande.demandeur:
            NotificationInterne.notifier(
                destinataire=demande.demandeur,
                titre=f"Décaissement #{demande.pk} refusé",
                message=(
                    f"Votre demande de décaissement de {demande.montant:,.0f} FC a été refusée "
                    f"par {request.user.get_full_name() or request.user.username}. "
                    f"Motif : {motif}"
                ),
                type_notification=NotificationInterne.REFUS,
                emetteur=request.user,
            )

        messages.warning(request, f"Décaissement #{demande.pk} refusé.")
        next_url = request.POST.get('next') or reverse('direction_cockpit')
        if is_htmx(request):
            response = HttpResponse()
            response['HX-Redirect'] = next_url
            return response
        return redirect(next_url)


# ── Gestion Utilisateurs (depuis le cockpit) ──────────────────────────────────

class DirectionUsersView(SuperAdminRequiredMixin, TemplateView):
    """Liste tous les utilisateurs du système."""
    template_name = 'direction/users_list.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['users'] = (
            CustomUser.objects
            .select_related('type_profile')
            .order_by('last_name', 'first_name')
        )
        return ctx


class DirectionUserToggleActiveView(SuperAdminRequiredMixin, View):
    """Active / Suspend un utilisateur."""
    def post(self, request, pk):
        user = get_object_or_404(CustomUser, pk=pk)
        if user == request.user:
            messages.error(request, "Vous ne pouvez pas désactiver votre propre compte.")
            return redirect('direction_users')
        user.is_active = not user.is_active
        user.save(update_fields=['is_active'])
        action = "activé" if user.is_active else "suspendu"
        messages.success(request, f"Utilisateur {user.username} {action}.")
        NotificationInterne.notifier(
            destinataire=user,
            titre=f"Votre compte a été {action}",
            message=f"L'administrateur a {action} votre accès au système.",
            type_notification=NotificationInterne.INFO,
            emetteur=request.user,
        )
        return redirect('direction_users')


class DirectionUserResetPasswordView(SuperAdminRequiredMixin, View):
    """Réinitialise le mot de passe d'un utilisateur vers '123456'."""
    def post(self, request, pk):
        user = get_object_or_404(CustomUser, pk=pk)
        new_password = request.POST.get('new_password', '').strip()
        if not new_password:
            messages.error(request, "Mot de passe vide non autorisé.")
            return redirect('direction_users')
        user.set_password(new_password)
        user.force_password_change = True
        user.save(update_fields=['password', 'force_password_change'])
        messages.success(
            request,
            f"Mot de passe de {user.username} réinitialisé. L'utilisateur devra le changer à la prochaine connexion."
        )
        NotificationInterne.notifier(
            destinataire=user,
            titre="Votre mot de passe a été réinitialisé",
            message="L'administrateur a réinitialisé votre mot de passe. Vous devez le changer lors de votre prochaine connexion.",
            type_notification=NotificationInterne.URGENT,
            emetteur=request.user,
        )
        return redirect('direction_users')


# ── Journal d'activité (depuis le cockpit) ────────────────────────────────────

class DirectionLogsView(SuperAdminRequiredMixin, TemplateView):
    """Journal d'activité des 200 dernières actions."""
    template_name = 'direction/logs.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        try:
            from activity_logs.models import ActivityLog
            ctx['logs'] = ActivityLog.objects.select_related('user').order_by('-created_at')[:200]
        except Exception:
            ctx['logs'] = []
        return ctx
