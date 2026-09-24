import datetime
import logging
from decimal import Decimal

from django.views import View
from django.views.generic import ListView, DetailView, FormView, DeleteView
from django.shortcuts import redirect, get_object_or_404, render, HttpResponse
from django.views.decorators.http import require_GET
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.urls import reverse_lazy, reverse
from django.template.loader import render_to_string
from django.core.exceptions import ValidationError, PermissionDenied
from .models import (Caisse, CaisseCourante, MouvementCaisse, RubriqueCaisse, SousRubriqueCaisse)
from clients.models import Client
from fournisseurs.models import Fournisseur
from creanciers.models import Creancier, Debiteur
from users.models import Caissier
from users.permissions import (
    CaisseAccessMixin, RoleRequiredMixin,
    ROLE_ADMIN, ROLE_CAISSIER, ROLE_GERANT_MAGASIN,
    user_has_role,
)
from paie.models import Agent
from .forms import OuvertureCaisseValidateForm, ClotureCaisseValidateForm, CaisseForm
from .selectors import get_total_ventes_caisse
from .services.mouvement_caisse import MouvementCaisseService

logger = logging.getLogger(__name__)

def get_total_entrees_caisse(caisse_courante, entrees):
    return caisse_courante.solde_initial + get_total_ventes_caisse(
        caisse_courante=caisse_courante
    ) + entrees


def assert_caisse_write_access(user, caisse: Caisse):
    if not user.is_authenticated:
        raise PermissionDenied
    if user_has_role(user, ROLE_ADMIN, ROLE_GERANT_MAGASIN):
        return
    if user_has_role(user, ROLE_CAISSIER):
        try:
            if user.caissier.caisse_id == caisse.pk:
                return
        except Caissier.DoesNotExist:
            pass
    raise PermissionDenied


class OuvertureCaisseView(CaisseAccessMixin, FormView):
    form_class = OuvertureCaisseValidateForm
    template_name = 'caisse/ouvrir_caisse.html'

    def get_caisse(self):
        """
        Returns the relevant Caisse for this request.
        If a pk is in the URL, use it directly. Otherwise fall back to the
        user's assigned caisse (caissier) or the principal caisse (admin/gérant).
        """
        try:
            caisse = Caisse.objects.get(pk=self.kwargs['pk'])
        except (Caisse.DoesNotExist, KeyError):
            if user_has_role(self.request.user, ROLE_ADMIN, ROLE_GERANT_MAGASIN):
                caisse = Caisse.objects.get(is_principal=True)
            else:
                check_caisse = Caissier.objects.get(user=self.request.user)
                caisse = Caisse.objects.get(pk=check_caisse.caisse.pk)
        return caisse

    def solde_initial(self):
        caisse = self.get_caisse()
        get_solde = CaisseCourante.objects.filter(caisse=caisse, est_ouverte=False).last()
        if not get_solde or get_solde.solde_final is None:
            return Decimal("0")
        return get_solde.solde_final

    def dispatch(self, request, *args, **kwargs):
        # Si cette caisse-là a déjà une instance ouverte, y rediriger directement.
        # On cible la caisse demandée (pas "n'importe quelle caisse ouverte de cet utilisateur")
        # pour permettre à un admin d'ouvrir plusieurs caisses indépendantes.
        caisse = self.get_caisse()
        instance_ouverte = CaisseCourante.objects.filter(
            caisse=caisse, est_ouverte=True
        ).first()
        if instance_ouverte:
            return redirect('caisse_details', instance_ouverte.pk)
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        caisse = self.get_caisse()
        nouvelle_caisse = CaisseCourante(
            caisse=caisse,
            ouvert_par=self.request.user,
            solde_initial=self.solde_initial()
        )
        nouvelle_caisse.save()
        return redirect('caisse_details', pk=nouvelle_caisse.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Ouverture caisse'
        context['message'] = 'Voulez-vous ouvrir la caisse ?'
        context['submit_icon'] = 'fa fa-check'
        context['submit_label'] = 'Oui'
        return context


def _render_champ_for_mouvement(mouvement):
    """Pre-render the dependent field partial with the correct entity pre-selected.

    Called when opening a movement for editing so the form shows the right
    client / agent / etc. without relying on the HTMX 'load' trigger (which
    would default to the first item in the list).
    """
    rubrique_nom = mouvement.rubrique.nom.lower() if mouvement.rubrique else ""

    if rubrique_nom == "clients":
        rel = mouvement.mouvements_caisse_c.first()
        selected_id = rel.client_id if rel else None
        return render_to_string("caisse/partials/field_client.html",
                                {"clients": Client.objects.all(), "selected_id": selected_id})

    if rubrique_nom == "fournisseurs":
        rel = mouvement.mouvements_caisse_f.first()
        selected_id = rel.fournisseur_id if rel else None
        return render_to_string("caisse/partials/field_fournisseur.html",
                                {"fournisseurs": Fournisseur.objects.all(), "selected_id": selected_id})

    if rubrique_nom == "créanciers":
        rel = mouvement.mouvements_caisse_cr.first()
        selected_id = rel.creancier_id if rel else None
        return render_to_string("caisse/partials/field_creancier.html",
                                {"creanciers": Creancier.objects.all(), "selected_id": selected_id})

    if rubrique_nom == "débiteurs":
        rel = mouvement.mouvements_caisse_db.first()
        selected_id = rel.debiteur_id if rel else None
        return render_to_string("caisse/partials/field_debiteur.html",
                                {"debiteurs": Debiteur.objects.all(), "selected_id": selected_id})

    if rubrique_nom == "transfert caisse":
        selected_id = mouvement.caisse_destination_id
        caisses = Caisse.objects.exclude(pk=mouvement.caisse.caisse_id)
        return render_to_string("caisse/partials/field_caisse.html",
                                {"caisses": caisses, "selected_id": selected_id})

    if rubrique_nom in MouvementCaisseService.AGENT_RUBRIQUES:
        rel = mouvement.mouvements_caisse_ag.first()
        selected_id = rel.agent_id if rel else None
        return render_to_string("caisse/partials/field_agent.html",
                                {"agents": Agent.objects.all(), "selected_id": selected_id})

    if (
        rubrique_nom == "charges exploitation"
        and mouvement.rubrique.classification_metier
        == RubriqueCaisse.ClassificationMetier.CHARGE_EXPLOITATION
    ):
        rel = mouvement.mouvements_caisse_ce.first()
        selected_id = (rel.sous_rubrique_id if rel else None) or mouvement.sous_rubrique_id
        return render_to_string("caisse/partials/field_sous_rubrique.html",
                                {"sous_rubriques": SousRubriqueCaisse.objects.filter(
                                    rubrique__nom="Charges exploitation"),
                                 "selected_id": selected_id})

    if (
        rubrique_nom == "charges personnelles"
        and mouvement.rubrique.classification_metier
        == RubriqueCaisse.ClassificationMetier.CHARGE_PERSONNELLE
    ):
        rel = mouvement.mouvements_caisse_cp.first()
        selected_id = (rel.sous_rubrique_id if rel else None) or mouvement.sous_rubrique_id
        return render_to_string("caisse/partials/field_sous_rubrique.html",
                                {"sous_rubriques": SousRubriqueCaisse.objects.filter(
                                    rubrique__nom="Charges personnelles"),
                                 "selected_id": selected_id})

    return ""


@login_required
@require_GET
def get_update_caisse_form(request, pk):
    instance = get_object_or_404(MouvementCaisse, pk=pk)
    assert_caisse_write_access(request.user, instance.caisse.caisse)
    form = CaisseForm(instance=instance, caisse_pk=instance.caisse.pk)
    prefilled_champ_html = _render_champ_for_mouvement(instance)
    return render(request, "caisse/partials/update_form.html",
                  {"update_form": form, "caisse_pk": instance.caisse.pk,
                   "mouvement_pk": pk, "prefilled_champ_html": prefilled_champ_html})


@login_required
@require_GET
def rubrique_champ_view(request, caisse_pk):
    # caisse_pk is the pk of CaisseCourante (the open session), not Caisse.
    caisse_courante = get_object_or_404(CaisseCourante, pk=caisse_pk)
    caisse = caisse_courante.caisse
    assert_caisse_write_access(request.user, caisse)
    logger.debug("rubrique_champ_view GET params: %s", request.GET)
    rubrique_id = request.GET.get('rubrique')
    champ_html = ""

    if rubrique_id:
        try:
            rubrique = RubriqueCaisse.objects.get(pk=rubrique_id)
        except RubriqueCaisse.DoesNotExist:
            return HttpResponse(champ_html)  # Rien à afficher

        if rubrique.nom.lower() == "clients":
            champ_html = render_to_string("caisse/partials/field_client.html",
                                          context={'clients': Client.objects.all()})

        elif rubrique.nom.lower() == "fournisseurs":
            champ_html = render_to_string("caisse/partials/field_fournisseur.html",
                                          context={'fournisseurs': Fournisseur.objects.all()})

        elif rubrique.nom.lower() == "créanciers":
            champ_html = render_to_string("caisse/partials/field_creancier.html",
                                          context={'creanciers': Creancier.objects.all()})

        elif rubrique.nom.lower() == "débiteurs":
            champ_html = render_to_string("caisse/partials/field_debiteur.html",
                                          context={'debiteurs': Debiteur.objects.all()})

        elif rubrique.nom.lower() == "transfert caisse":
            caisses = Caisse.objects.exclude(pk=caisse.pk)
            champ_html = render_to_string("caisse/partials/field_caisse.html",
                                          context={'caisses': caisses})

        elif rubrique.nom.lower() in MouvementCaisseService.AGENT_RUBRIQUES:
            champ_html = render_to_string("caisse/partials/field_agent.html",
                                          context={'agents': Agent.objects.all()})

        elif (
            rubrique.nom.lower() == "charges exploitation"
            and rubrique.classification_metier
            == RubriqueCaisse.ClassificationMetier.CHARGE_EXPLOITATION
        ):
            champ_html = render_to_string("caisse/partials/field_sous_rubrique.html",
                                          context={'sous_rubriques': SousRubriqueCaisse.objects.filter(rubrique__nom="Charges exploitation")})

        elif (
            rubrique.nom.lower() == "charges personnelles"
            and rubrique.classification_metier
            == RubriqueCaisse.ClassificationMetier.CHARGE_PERSONNELLE
        ):
            champ_html = render_to_string("caisse/partials/field_sous_rubrique.html",
                                          context={'sous_rubriques': SousRubriqueCaisse.objects.filter(rubrique__nom="Charges personnelles")})


    return HttpResponse(champ_html)


class CaisseView(CaisseAccessMixin, DetailView):
    model = CaisseCourante
    context_object_name = "caisse_courante"
    template_name = "caisse/caisse.html"
    success_url = reverse_lazy("historique_caisse")

    def get_caisse(self):
        return get_object_or_404(CaisseCourante, pk=self.kwargs['pk']).caisse

    # ---------- helpers vue ----------

    def mouvements(self, type_mouvement):
        return (
            MouvementCaisse.objects
            .filter(caisse=self.object, type_mouvement=type_mouvement)
            .select_related("rubrique", "sous_rubrique", "caisse_destination", "effectue_par")
            .prefetch_related(
                "mouvements_caisse_f__fournisseur",
                "mouvements_caisse_c__client",
                "mouvements_caisse_cr__creancier",
                "mouvements_caisse_db__debiteur",
                "mouvements_caisse_ag__agent",
                "mouvements_caisse_ce__sous_rubrique",
                "mouvements_caisse_cp__sous_rubrique",
            )
        )

    def total_entrees(self):
        return get_total_entrees_caisse(
            self.object,
            MouvementCaisseService.total_par_type(self.object, "ENTREE"),
        )

    def total_sorties(self):
        return MouvementCaisseService.total_par_type(self.object, "SORTIE")

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        context = self.get_context_data(object=self.object)

        # formulaire affiché au chargement
        context["add_form"] = CaisseForm(
            caisse_pk=self.object.pk
        )

        return self.render_to_response(context)

    def render_state(self, request, error_message=None):
        ventes = get_total_ventes_caisse(caisse_courante=self.object)
        total_entrees = self.total_entrees()
        total_sorties = self.total_sorties()

        ctx = {
            "add_form": CaisseForm(caisse_pk=self.object.pk),
            "caisse": self.object.caisse,
            "caisse_courante": self.object,
            "ventes": ventes,
            "mouvements_entree": self.mouvements("ENTREE"),
            "mouvements_sortie": self.mouvements("SORTIE"),
            "total_entrees": total_entrees,
            "total_sorties": total_sorties,
        }
        if error_message:
            ctx["error_message"] = error_message

        html = render_to_string(
            "caisse/partials/add_form_and_table.html",
            ctx,
            request=request,
        )

        html_totaux = render_to_string(
            "caisse/partials/caisse_totaux_oob.html",
            {
                "total_entrees": total_entrees,
                "total_sorties": total_sorties,
                "solde_caisse": total_entrees - total_sorties,
            },
        )

        return HttpResponse(html + html_totaux)

    def _ids_from_post(self, post):
        return {
            "fournisseur_id": post.get("fournisseur"),
            "client_id": post.get("client"),
            "creancier_id": post.get("creancier"),
            "debiteur_id": post.get("debiteur"),
            "agent_id": post.get("agent"),
            "sous_rubrique_id": post.get("sous_rubrique"),
            "caisse_destination_id": post.get("caisse_destination"),
        }

    def post(self, request, *args, **kwargs):
        if request.headers.get("HX-Request") != "true":
            return JsonResponse({"error": "Invalid request"}, status=400)

        self.object = self.get_object()
        form_type = request.POST.get("form_type")

        if form_type == "add":
            form = CaisseForm(request.POST, caisse_pk=self.object.pk)
            if not form.is_valid():
                return JsonResponse({"success": False, "errors": form.errors}, status=400)

            try:
                MouvementCaisseService.create(
                    form=form,
                    caisse_courante=self.object,
                    user=request.user,
                    **self._ids_from_post(request.POST),
                )
            except ValidationError as e:
                resp = self.render_state(request, error_message=str(e))
                resp.status_code = 400
                return resp

            return self.render_state(request)

        mouvement = get_object_or_404(MouvementCaisse, pk=request.POST.get("id"))
        form = CaisseForm(
            request.POST,
            instance=mouvement,
            caisse_pk=self.object.pk,
        )
        if not form.is_valid():
            return JsonResponse({"success": False, "errors": form.errors}, status=400)

        try:
            MouvementCaisseService.update(
                form=form,
                user=request.user,
                **self._ids_from_post(request.POST),
            )
        except ValidationError as e:
            resp = self.render_state(request, error_message=str(e))
            resp.status_code = 400
            return resp

        return self.render_state(request)

    def get_context_data(self, **kwargs):
        self.object = self.get_object()
        ctx = super().get_context_data(**kwargs)

        total_entrees = self.total_entrees()
        total_sorties = self.total_sorties()

        from .models import DemandeDecaissement
        nb_approuves = DemandeDecaissement.objects.filter(
            caisse=self.object, statut=DemandeDecaissement.APPROUVEE
        ).count()
        nb_attente = DemandeDecaissement.objects.filter(
            caisse=self.object, statut=DemandeDecaissement.EN_ATTENTE
        ).count()

        ctx.update({
            "caisse": self.object.caisse,
            "mouvements_entree": self.mouvements("ENTREE"),
            "mouvements_sortie": self.mouvements("SORTIE"),
            "ventes": get_total_ventes_caisse(caisse_courante=self.object),
            "total_entrees": total_entrees,
            "total_sorties": total_sorties,
            "solde_caisse": total_entrees - total_sorties,
            "nb_decaissements_approuves": nb_approuves,
            "nb_decaissements_en_attente": nb_attente,
        })
        return ctx


class ClotureCaisseView(CaisseAccessMixin, FormView):
    form_class = ClotureCaisseValidateForm
    template_name = 'caisse/cloturer_caisse.html'

    def get_caisse(self):
        return self.get_caisse_courante().caisse

    def get_caisse_courante(self):
        """
        """
        caisse_courante = CaisseCourante.objects.get(pk=self.kwargs['pk'])
        return caisse_courante

    def get_mouvements_entree_caisse(self):
        mouvements_qs = MouvementCaisse.objects.filter(caisse=self.get_caisse_courante().pk, type_mouvement='ENTREE')
        return sum(i.montant for i in mouvements_qs)

    def get_mouvements_sortie_caisse(self):
        mouvements_qs = MouvementCaisse.objects.filter(caisse=self.get_caisse_courante().pk, type_mouvement='SORTIE')
        return sum(i.montant for i in mouvements_qs)

    def solde_final(self):
        caisse_courante = self.get_caisse_courante()
        entrees = self.get_mouvements_entree_caisse()
        sorties = self.get_mouvements_sortie_caisse()
        solde_final = get_total_entrees_caisse(caisse_courante, entrees) - sorties
        return solde_final

    def post(self, request, *args, **kwargs):
        caisse_courante = self.get_caisse_courante()
        caisse_courante.solde_final = self.solde_final()
        caisse_courante.ferme_par = self.request.user
        caisse_courante.date_fermeture = datetime.datetime.now()
        caisse_courante.est_ouverte = False
        caisse_courante.save()

        if user_has_role(self.request.user, ROLE_ADMIN):
            caisse = Caisse.objects.get(is_principal=True)
            # Redirection vers l'historique
            response = HttpResponse()
            response["HX-Redirect"] = reverse('historique_caisse', kwargs={'pk': caisse.pk})
            return response

        else:
            response = HttpResponse()
            response["HX-Redirect"] = reverse('index')
            return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Clôture caisse'
        context['message'] = 'Êtes-vous sûr de vouloir clôturer cette caisse ? Cette action est irréversible.'
        context['submit_icon'] = 'fa fa-check'
        context['submit_label'] = 'Oui'
        context['solde_final'] = self.solde_final()
        context['caisse_courante'] = self.get_caisse_courante()
        return context


class MouvementCaisseDeleteView(CaisseAccessMixin, DeleteView):
    model = MouvementCaisse
    context_object_name = "mouvement_caisse"
    template_name = "caisse/mouvement_caisse_confirm_delete.html"

    def get_caisse_courante(self):
        return get_object_or_404(CaisseCourante, pk=self.kwargs["caisse_pk"])

    def get_caisse(self):
        return self.get_caisse_courante().caisse

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            "title": "Supprimer un mouvement de caisse",
            "message": (
                f"Êtes-vous sûr de vouloir supprimer le mouvement : "
                f"#{self.object.motif} ? Cette action est irréversible."
            ),
            "submit_icon": "fa fa-check",
            "submit_label": "Valider",
            "caisse": self.get_caisse_courante(),
        })
        return ctx

    def delete(self, request, *args, **kwargs):
        mouvement = self.get_object()
        caisse_courante = mouvement.caisse

        try:
            MouvementCaisseService.delete(mouvement=mouvement)
        except ValidationError as e:
            return HttpResponse(
                f"<div class='alert alert-danger'><i class='fa fa-exclamation-triangle'></i> {str(e)}</div>",
                status=400,
            )

        # Re-render UI from DB state (source of truth)
        mouvements_entree = MouvementCaisse.objects.filter(caisse=caisse_courante, type_mouvement='ENTREE')
        mouvements_sortie = MouvementCaisse.objects.filter(caisse=caisse_courante, type_mouvement='SORTIE')

        ventes = get_total_ventes_caisse(caisse_courante=caisse_courante)
        total_entrees = get_total_entrees_caisse(
            caisse_courante,
            sum(m.montant for m in mouvements_entree),
        )
        total_sorties = sum(m.montant for m in mouvements_sortie)

        html_table = render_to_string(
            "caisse/partials/lines_table.html",
            {
                "caisse": self.get_caisse(),
                "caisse_courante": caisse_courante,
                "ventes": ventes,
                "mouvements_entree": mouvements_entree,
                "mouvements_sortie": mouvements_sortie,
                "total_entrees": total_entrees,
                "total_sorties": total_sorties,
            },
            request=request,
        )

        html_totaux = render_to_string(
            "caisse/partials/caisse_totaux_oob.html",
            {
                "solde_caisse": total_entrees - total_sorties,
                "total_entrees": total_entrees,
                "total_sorties": total_sorties,
            },
            request=request,
        )

        response = HttpResponse(html_table + html_totaux)
        response["HX-Trigger"] = "closeModal"
        return response


class CaissesView(RoleRequiredMixin, ListView):
    model = Caisse
    context_object_name = 'liste_caisses'
    template_name = 'caisse/caisses.html'
    allowed_roles = [ROLE_ADMIN, ROLE_CAISSIER, ROLE_GERANT_MAGASIN]

    def get_queryset(self):
        user = self.request.user
        if user_has_role(user, ROLE_ADMIN, ROLE_GERANT_MAGASIN):
            return Caisse.objects.all()
        try:
            check_caisse = Caissier.objects.get(user=user)
            return Caisse.objects.filter(pk=check_caisse.caisse.pk)
        except Caissier.DoesNotExist:
            return Caisse.objects.none()


class HistoriqueCaisseView(RoleRequiredMixin, DetailView):
    allowed_roles = [ROLE_ADMIN, ROLE_CAISSIER, ROLE_GERANT_MAGASIN]
    model = Caisse
    template_name = 'caisse/caisse_historique.html'

    def get_liste_caisses_courantes(self):
        return CaisseCourante.objects.filter(caisse=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['caisse'] = self.object
        context['liste_caisses'] = self.get_liste_caisses_courantes()
        return context


# ═══════════════════════════════════════════════════════════════════════════════
# CIRCUIT DÉCAISSEMENT — Vues Caissier
# ═══════════════════════════════════════════════════════════════════════════════

class DemandeDecaissementCreateView(CaisseAccessMixin, View):
    """
    Le caissier soumet une demande de décaissement.
    RÈGLE MÉDICO-LÉGALE : aucun MouvementCaisse n'est créé ici.
    La demande part directement au statut EN_ATTENTE pour validation Direction.
    """
    template_name = 'caisse/decaissement_form.html'

    def get_caisse(self):
        return get_object_or_404(CaisseCourante, pk=self.kwargs['pk'])

    def get(self, request, pk):
        from .forms import DemandeDecaissementForm
        caisse_courante = self.get_caisse()
        form = DemandeDecaissementForm(caisse_pk=caisse_courante.pk)
        return render(request, self.template_name, {
            'form': form,
            'caisse_courante': caisse_courante,
            'title': 'Nouvelle demande de décaissement',
        })

    def post(self, request, pk):
        from .forms import DemandeDecaissementForm
        from notifications.models import NotificationInterne
        from django.db import transaction

        caisse_courante = self.get_caisse()
        assert_caisse_write_access(request.user, caisse_courante.caisse)

        form = DemandeDecaissementForm(request.POST, caisse_pk=caisse_courante.pk)
        if not form.is_valid():
            return render(request, self.template_name, {
                'form': form,
                'caisse_courante': caisse_courante,
                'title': 'Nouvelle demande de décaissement',
            })

        with transaction.atomic():
            from .models import DemandeDecaissement
            demande = DemandeDecaissement.objects.create(
                caisse=caisse_courante,
                demandeur=request.user,
                montant=form.cleaned_data['montant'],
                rubrique=form.cleaned_data['rubrique'],
                sous_rubrique=form.cleaned_data.get('sous_rubrique'),
                motif=form.cleaned_data['motif'],
                reference=form.cleaned_data.get('reference') or '',
                fournisseur=form.cleaned_data.get('fournisseur'),
                client=form.cleaned_data.get('client'),
                creancier=form.cleaned_data.get('creancier'),
                agent=form.cleaned_data.get('agent'),
                statut=DemandeDecaissement.EN_ATTENTE,
            )
            # Notification superadmins
            NotificationInterne.notifier_superadmins(
                titre=f"Demande de décaissement #{demande.pk} — {demande.montant:,.0f} FC",
                message=(
                    f"{request.user.username} demande un décaissement de {demande.montant:,.0f} FC "
                    f"sur la caisse « {caisse_courante.caisse.nom} ».\n"
                    f"Rubrique : {demande.rubrique.nom}\n"
                    f"Motif : {demande.motif}"
                ),
                type_notification=NotificationInterne.INFO,
                emetteur=request.user,
                lien=reverse('direction_cockpit'),
            )

        from django.contrib import messages as dj_messages
        dj_messages.success(
            request,
            f"Demande de décaissement #{demande.pk} soumise à la Direction. Vous serez notifié dès qu'une décision sera prise."
        )
        return redirect('caisse_details', pk=caisse_courante.pk)


class DemandeDecaissementExecuterView(CaisseAccessMixin, View):
    """
    Le caissier exécute physiquement un décaissement APPROUVÉ.
    C'est ICI et SEULEMENT ICI qu'un MouvementCaisse de type SORTIE est créé.
    RÈGLE MÉDICO-LÉGALE ABSOLUE : vérifier statut == APPROUVEE avant tout.
    """
    def get_caisse(self):
        demande = get_object_or_404(
            __import__('caisse.models', fromlist=['DemandeDecaissement']).DemandeDecaissement,
            pk=self.kwargs['pk']
        )
        return demande.caisse.caisse

    def post(self, request, pk):
        from .models import DemandeDecaissement
        from notifications.models import NotificationInterne
        from django.db import transaction

        demande = get_object_or_404(DemandeDecaissement, pk=pk)
        caisse_courante = demande.caisse
        assert_caisse_write_access(request.user, caisse_courante.caisse)

        # ── Vérifications médico-légales ──
        if demande.statut != DemandeDecaissement.APPROUVEE:
            from django.contrib import messages as dj_messages
            dj_messages.error(
                request,
                "Cette demande n'est pas approuvée par la Direction. Vous ne pouvez pas l'exécuter."
            )
            return redirect('caisse_details', pk=caisse_courante.pk)

        if not caisse_courante.est_ouverte:
            from django.contrib import messages as dj_messages
            dj_messages.error(request, "La caisse est fermée.")
            return redirect('caisse_details', pk=caisse_courante.pk)

        montant_final = demande.montant_final

        # ── Création atomique du MouvementCaisse ──
        with transaction.atomic():
            # Construire un CaisseForm synthétique pour passer par MouvementCaisseService
            class _FakeForm:
                """Adaptateur minimal pour MouvementCaisseService.create()"""
                def __init__(self, demande, montant):
                    self.cleaned_data = {
                        'type_mouvement': 'SORTIE',
                        'montant': montant,
                        'rubrique': demande.rubrique,
                        'sous_rubrique': demande.sous_rubrique,
                        'motif': f"Décaissement #{demande.pk} — {demande.motif}",
                        'reference': demande.reference or '',
                        'devise': None,
                        'taux': None,
                        'caisse_destination': None,
                    }

            fake_form = _FakeForm(demande, montant_final)
            try:
                mouvement = MouvementCaisseService.create(
                    form=fake_form,
                    caisse_courante=caisse_courante,
                    user=request.user,
                    fournisseur_id=demande.fournisseur_id,
                    client_id=demande.client_id,
                    creancier_id=demande.creancier_id,
                    debiteur_id=demande.debiteur_id,
                    agent_id=demande.agent_id,
                    sous_rubrique_id=demande.sous_rubrique_id,
                    caisse_destination_id=None,
                )
            except ValidationError as e:
                from django.contrib import messages as dj_messages
                dj_messages.error(request, str(e))
                return redirect('caisse_details', pk=caisse_courante.pk)

            # Lier le mouvement à la demande et marquer EXECUTEE
            from django.utils import timezone
            demande.mouvement_caisse = mouvement
            demande.statut = DemandeDecaissement.EXECUTEE
            demande.date_execution = timezone.now()
            demande.save(update_fields=['mouvement_caisse', 'statut', 'date_execution'])

            # Notification au superadmin : exécution effectuée
            NotificationInterne.notifier_superadmins(
                titre=f"Décaissement #{demande.pk} exécuté — {montant_final:,.0f} FC",
                message=(
                    f"{request.user.username} a exécuté le décaissement approuvé #{demande.pk} "
                    f"({montant_final:,.0f} FC) sur la caisse « {caisse_courante.caisse.nom} »."
                ),
                type_notification=NotificationInterne.INFO,
                emetteur=request.user,
                lien=reverse('direction_cockpit'),
            )

        from django.contrib import messages as dj_messages
        dj_messages.success(
            request,
            f"Décaissement #{demande.pk} exécuté avec succès — {montant_final:,.0f} FC débité de la caisse."
        )
        return redirect('caisse_details', pk=caisse_courante.pk)


class DemandesDecaissementListView(CaisseAccessMixin, View):
    """
    Liste les demandes de décaissement d'une caisse courante donnée.
    Filtrée par caisse et accessible au caissier concerné ou admin.
    """
    template_name = 'caisse/decaissement_list.html'

    def get_caisse(self):
        return get_object_or_404(CaisseCourante, pk=self.kwargs['pk'])

    def get(self, request, pk):
        from .models import DemandeDecaissement
        caisse_courante = self.get_caisse()
        assert_caisse_write_access(request.user, caisse_courante.caisse)
        demandes = (
            DemandeDecaissement.objects
            .filter(caisse=caisse_courante)
            .select_related('demandeur', 'rubrique', 'valide_par', 'mouvement_caisse')
            .order_by('-date_demande')
        )
        return render(request, self.template_name, {
            'caisse_courante': caisse_courante,
            'demandes': demandes,
        })


class DemandeDecaissementPdfView(CaisseAccessMixin, View):
    """
    Génère le Manifeste officiel de décaissement & Bon de sortie de caisse (PDF).
    Disponible pour le caissier et la direction dès que la demande est approuvée ou exécutée.
    """
    def get_caisse(self):
        demande = get_object_or_404(
            __import__('caisse.models', fromlist=['DemandeDecaissement']).DemandeDecaissement,
            pk=self.kwargs['pk']
        )
        return demande.caisse.caisse

    def get(self, request, pk):
        from .models import DemandeDecaissement
        from .pdf import generer_manifeste_decaissement_pdf
        demande = get_object_or_404(DemandeDecaissement, pk=pk)
        return generer_manifeste_decaissement_pdf(demande=demande, request=request)