from django.db import models
from decimal import Decimal

class Caisse(models.Model):
    nom = models.CharField(max_length=150)
    is_principal = models.BooleanField(default=False)
    objects = models.Manager()

    def __str__(self):
        return self.nom


class CaisseCourante(models.Model):
    caisse = models.ForeignKey(Caisse, on_delete=models.CASCADE, related_name='caisses')
    ouvert_par = models.ForeignKey('users.CustomUser', on_delete=models.SET_NULL, null=True,
                                   related_name='ouvertures_caisse')
    ferme_par = models.ForeignKey('users.CustomUser', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='fermetures_caisse')
    date_ouverture = models.DateTimeField(auto_now_add=True)
    date_fermeture = models.DateTimeField(null=True, blank=True)
    solde_initial = models.DecimalField(max_digits=18, decimal_places=2)
    solde_initial_usd = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True,
                                            help_text="Valeur USD du solde initial au taux d'ouverture")
    taux_ouverture = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True,
                                         help_text="Taux historique à l'ouverture")
    solde_final = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    solde_final_usd = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True,
                                          help_text="Valeur USD du solde final au taux de fermeture")
    taux_fermeture = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True,
                                         help_text="Taux historique à la fermeture")
    est_ouverte = models.BooleanField(default=True)
    objects = models.Manager()

    def __str__(self):
        return f"Caisse #{self.id} - {self.date_ouverture.date()}"

    def save(self, *args, **kwargs):
        from parametres.models import get_taux_usd_cdf
        if not self.pk and self.solde_initial_usd is None and self.solde_initial:
            try:
                taux = get_taux_usd_cdf(self.date_ouverture.date() if self.date_ouverture else None)
                self.taux_ouverture = taux
                self.solde_initial_usd = Decimal(str(self.solde_initial)) / taux if taux else Decimal('0')
            except Exception:
                pass
        super().save(*args, **kwargs)


class RubriqueCaisse(models.Model):
    class ClassificationMetier(models.TextChoices):
        NONE = "NONE", "Aucune"
        CHARGE_EXPLOITATION = (
            "CHARGE_EXPLOITATION",
            "Charge d'exploitation",
        )
        CHARGE_PERSONNELLE = "CHARGE_PERSONNELLE", "Charge personnelle"

    nom = models.CharField(max_length=150)
    description = models.TextField()
    visible = models.BooleanField(default=True)
    classification_metier = models.CharField(
        max_length=32,
        choices=ClassificationMetier.choices,
        default=ClassificationMetier.NONE,
        db_index=True,
    )
    objects = models.Manager()

    def __str__(self):
        return f"{self.nom}"


class SousRubriqueCaisse(models.Model):
    rubrique = models.ForeignKey(RubriqueCaisse, on_delete=models.CASCADE, related_name='sous_rubriques')
    nom = models.CharField(max_length=45)
    description = models.TextField()
    objects = models.Manager()

    def __str__(self):
        return f"{self.nom}"


class MouvementCaisse(models.Model):
    TYPE_CHOICES = [
        ('ENTREE', 'Entrée'),
        ('SORTIE', 'Sortie'),
    ]

    caisse = models.ForeignKey(CaisseCourante, on_delete=models.CASCADE, related_name='mouvements')
    type_mouvement = models.CharField(max_length=10, choices=TYPE_CHOICES)
    rubrique = models.ForeignKey(RubriqueCaisse, on_delete=models.PROTECT, related_name='mouvements_rubrique')
    sous_rubrique = models.ForeignKey(SousRubriqueCaisse, on_delete=models.PROTECT, null=True, blank=True)
    caisse_destination = models.ForeignKey(
        'Caisse', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='transferts_sortants',
    )
    mouvement_transfert_source = models.OneToOneField(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='mouvement_transfert_miroir',
    )
    montant = models.DecimalField(max_digits=18, decimal_places=2)
    montant_usd = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True,
                                      help_text="Valeur USD historique du mouvement")
    taux_mouvement = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True,
                                         help_text="Taux de change historique au moment du mouvement")
    motif = models.CharField(max_length=255)
    reference = models.CharField(max_length=100, blank=True, null=True)
    effectue_par = models.ForeignKey('users.CustomUser', on_delete=models.SET_NULL, null=True)
    date_mouvement = models.DateTimeField(auto_now_add=True)
    objects = models.Manager()

    class Meta:
        ordering = ['date_mouvement']
        indexes = [
            models.Index(fields=['date_mouvement']),
            models.Index(fields=['type_mouvement']),
        ]

    def __str__(self):
        return f"{self.type_mouvement} - {self.montant}"

    def save(self, *args, **kwargs):
        from parametres.models import get_taux_usd_cdf
        creating = self.pk is None
        if creating and self.montant_usd is None and self.montant:
            try:
                date_val = self.date_mouvement.date() if self.date_mouvement else None
                taux = get_taux_usd_cdf(date_val)
                self.taux_mouvement = taux
                self.montant_usd = Decimal(str(self.montant)) / taux if taux else Decimal('0')
            except Exception:
                pass
        else:
            original = MouvementCaisse.objects.filter(pk=self.pk).first()
            if original:
                self.taux_mouvement = original.taux_mouvement
                self.montant_usd = original.montant_usd
        super().save(*args, **kwargs)

    @property
    def badge_entite(self):
        if self.caisse_destination_id:
            return str(self.caisse_destination)

        if self.sous_rubrique_id:
            return str(self.sous_rubrique)

        for related, field in (
            ("mouvements_caisse_f", "fournisseur"),
            ("mouvements_caisse_c", "client"),
            ("mouvements_caisse_cr", "creancier"),
            ("mouvements_caisse_db", "debiteur"),
            ("mouvements_caisse_ag", "agent"),
            ("mouvements_caisse_ce", "sous_rubrique"),
            ("mouvements_caisse_cp", "sous_rubrique"),
        ):
            qs = getattr(self, related).all()
            if qs:
                return str(getattr(qs[0], field))

        return None


class MouvementCaisseFournisseur(models.Model):
    mouvement_caisse = models.ForeignKey(MouvementCaisse, on_delete=models.CASCADE, related_name='mouvements_caisse_f')
    fournisseur = models.ForeignKey('fournisseurs.Fournisseur', on_delete=models.CASCADE, related_name='fournisseur')
    valeur_usd = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    taux_paiement = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    objects = models.Manager()

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.pk:
            original = MouvementCaisseFournisseur.objects.filter(pk=self.pk).first()
            if original:
                if self.taux_paiement is not None and self.taux_paiement != original.taux_paiement:
                    raise ValidationError("Le taux de paiement historique ne peut pas être modifié.")
                if self.valeur_usd is not None and self.valeur_usd != original.valeur_usd:
                    raise ValidationError("La valeur USD historique ne peut pas être modifiée.")
        return super().clean()

    def save(self, *args, **kwargs):
        from decimal import Decimal
        from parametres.models import get_taux_usd_cdf

        creating = self.pk is None
        if creating:
            if self.taux_paiement is None:
                date_m = None
                if self.mouvement_caisse and self.mouvement_caisse.date_mouvement:
                    date_m = self.mouvement_caisse.date_mouvement.date()
                self.taux_paiement = get_taux_usd_cdf(date_m)
            if self.valeur_usd is None and self.mouvement_caisse:
                montant_fc = Decimal(str(self.mouvement_caisse.montant))
                self.valeur_usd = montant_fc / self.taux_paiement if self.taux_paiement else Decimal('0')
        else:
            original = MouvementCaisseFournisseur.objects.filter(pk=self.pk).first()
            if original:
                self.taux_paiement = original.taux_paiement
                self.valeur_usd = original.valeur_usd
        super().save(*args, **kwargs)


class MouvementCaisseClient(models.Model):
    mouvement_caisse = models.ForeignKey(MouvementCaisse, on_delete=models.CASCADE, related_name='mouvements_caisse_c')
    client = models.ForeignKey('clients.Client', on_delete=models.CASCADE, related_name='client')
    valeur_usd = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    taux_paiement = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    objects = models.Manager()

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.pk:
            original = MouvementCaisseClient.objects.filter(pk=self.pk).first()
            if original:
                if self.taux_paiement is not None and self.taux_paiement != original.taux_paiement:
                    raise ValidationError("Le taux de paiement historique ne peut pas être modifié.")
                if self.valeur_usd is not None and self.valeur_usd != original.valeur_usd:
                    raise ValidationError("La valeur USD historique ne peut pas être modifiée.")
        return super().clean()

    def save(self, *args, **kwargs):
        from decimal import Decimal
        from parametres.models import get_taux_usd_cdf

        creating = self.pk is None
        if creating:
            if self.taux_paiement is None:
                date_m = None
                if self.mouvement_caisse and self.mouvement_caisse.date_mouvement:
                    date_m = self.mouvement_caisse.date_mouvement.date()
                self.taux_paiement = get_taux_usd_cdf(date_m)
            if self.valeur_usd is None and self.mouvement_caisse:
                montant_fc = Decimal(str(self.mouvement_caisse.montant))
                self.valeur_usd = montant_fc / self.taux_paiement if self.taux_paiement else Decimal('0')
        else:
            original = MouvementCaisseClient.objects.filter(pk=self.pk).first()
            if original:
                self.taux_paiement = original.taux_paiement
                self.valeur_usd = original.valeur_usd
        super().save(*args, **kwargs)


class MouvementCaisseCreancier(models.Model):
    mouvement_caisse = models.ForeignKey(MouvementCaisse, on_delete=models.CASCADE, related_name='mouvements_caisse_cr')
    creancier = models.ForeignKey('creanciers.Creancier', on_delete=models.CASCADE, related_name='creancier')
    valeur_usd = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    taux_paiement = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    objects = models.Manager()

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.pk:
            original = MouvementCaisseCreancier.objects.filter(pk=self.pk).first()
            if original:
                if self.taux_paiement is not None and self.taux_paiement != original.taux_paiement:
                    raise ValidationError("Le taux de paiement historique ne peut pas être modifié.")
                if self.valeur_usd is not None and self.valeur_usd != original.valeur_usd:
                    raise ValidationError("La valeur USD historique ne peut pas être modifiée.")
        return super().clean()

    def save(self, *args, **kwargs):
        from decimal import Decimal
        from parametres.models import get_taux_usd_cdf

        creating = self.pk is None
        if creating:
            if self.taux_paiement is None:
                date_m = None
                if self.mouvement_caisse and self.mouvement_caisse.date_mouvement:
                    date_m = self.mouvement_caisse.date_mouvement.date()
                self.taux_paiement = get_taux_usd_cdf(date_m)
            if self.valeur_usd is None and self.mouvement_caisse:
                montant_fc = Decimal(str(self.mouvement_caisse.montant))
                self.valeur_usd = montant_fc / self.taux_paiement if self.taux_paiement else Decimal('0')
        else:
            original = MouvementCaisseCreancier.objects.filter(pk=self.pk).first()
            if original:
                self.taux_paiement = original.taux_paiement
                self.valeur_usd = original.valeur_usd
        super().save(*args, **kwargs)


class MouvementCaisseDebiteur(models.Model):
    mouvement_caisse = models.ForeignKey(MouvementCaisse, on_delete=models.CASCADE, related_name='mouvements_caisse_db')
    debiteur = models.ForeignKey('creanciers.Debiteur', on_delete=models.CASCADE, related_name='debiteur')
    valeur_usd = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    taux_paiement = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    objects = models.Manager()

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.pk:
            original = MouvementCaisseDebiteur.objects.filter(pk=self.pk).first()
            if original:
                if self.taux_paiement is not None and self.taux_paiement != original.taux_paiement:
                    raise ValidationError("Le taux de paiement historique ne peut pas être modifié.")
                if self.valeur_usd is not None and self.valeur_usd != original.valeur_usd:
                    raise ValidationError("La valeur USD historique ne peut pas être modifiée.")
        return super().clean()

    def save(self, *args, **kwargs):
        from decimal import Decimal
        from parametres.models import get_taux_usd_cdf

        creating = self.pk is None
        if creating:
            if self.taux_paiement is None:
                date_m = None
                if self.mouvement_caisse and self.mouvement_caisse.date_mouvement:
                    date_m = self.mouvement_caisse.date_mouvement.date()
                self.taux_paiement = get_taux_usd_cdf(date_m)
            if self.valeur_usd is None and self.mouvement_caisse:
                montant_fc = Decimal(str(self.mouvement_caisse.montant))
                self.valeur_usd = montant_fc / self.taux_paiement if self.taux_paiement else Decimal('0')
        else:
            original = MouvementCaisseDebiteur.objects.filter(pk=self.pk).first()
            if original:
                self.taux_paiement = original.taux_paiement
                self.valeur_usd = original.valeur_usd
        super().save(*args, **kwargs)


class MouvementCaisseAgent(models.Model):
    mouvement_caisse = models.ForeignKey(MouvementCaisse, on_delete=models.CASCADE, related_name='mouvements_caisse_ag')
    agent = models.ForeignKey('paie.Agent', on_delete=models.CASCADE, related_name='agent')
    valeur_usd = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True,
                                     help_text="Valeur USD historique du paiement")
    taux_paiement = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True,
                                        help_text="Taux historique au moment du paiement")
    objects = models.Manager()

    def save(self, *args, **kwargs):
        from decimal import Decimal
        from parametres.models import get_taux_usd_cdf

        creating = self.pk is None
        if creating:
            if self.taux_paiement is None:
                date_m = None
                if self.mouvement_caisse and self.mouvement_caisse.date_mouvement:
                    date_m = self.mouvement_caisse.date_mouvement.date()
                self.taux_paiement = get_taux_usd_cdf(date_m)
            if self.valeur_usd is None and self.mouvement_caisse:
                montant_fc = Decimal(str(self.mouvement_caisse.montant))
                self.valeur_usd = montant_fc / self.taux_paiement if self.taux_paiement else Decimal('0')
        else:
            original = MouvementCaisseAgent.objects.filter(pk=self.pk).first()
            if original:
                self.taux_paiement = original.taux_paiement
                self.valeur_usd = original.valeur_usd
        super().save(*args, **kwargs)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.pk:
            original = MouvementCaisseAgent.objects.filter(pk=self.pk).first()
            if original:
                if self.taux_paiement is not None and self.taux_paiement != original.taux_paiement:
                    raise ValidationError("Le taux de paiement historique ne peut pas être modifié.")
                if self.valeur_usd is not None and self.valeur_usd != original.valeur_usd:
                    raise ValidationError("La valeur USD historique ne peut pas être modifiée.")
        return super().clean()


class MouvementCaisseChargesExploitation(models.Model):
    mouvement_caisse = models.ForeignKey(MouvementCaisse, on_delete=models.CASCADE, related_name='mouvements_caisse_ce')
    sous_rubrique = models.ForeignKey(SousRubriqueCaisse, on_delete=models.CASCADE, related_name='sous_rubrique_ce')
    valeur_usd = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True,
                                     help_text="Valeur USD historique de la charge")
    taux_mouvement = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True,
                                         help_text="Taux historique au moment de la charge")
    objects = models.Manager()

    def save(self, *args, **kwargs):
        from decimal import Decimal
        from parametres.models import get_taux_usd_cdf

        creating = self.pk is None
        if creating:
            if self.taux_mouvement is None:
                date_m = None
                if self.mouvement_caisse and self.mouvement_caisse.date_mouvement:
                    date_m = self.mouvement_caisse.date_mouvement.date()
                self.taux_mouvement = get_taux_usd_cdf(date_m)
            if self.valeur_usd is None and self.mouvement_caisse:
                montant_fc = Decimal(str(self.mouvement_caisse.montant))
                self.valeur_usd = montant_fc / self.taux_mouvement if self.taux_mouvement else Decimal('0')
        else:
            original = MouvementCaisseChargesExploitation.objects.filter(pk=self.pk).first()
            if original:
                self.taux_mouvement = original.taux_mouvement
                self.valeur_usd = original.valeur_usd
        super().save(*args, **kwargs)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.pk:
            original = MouvementCaisseChargesExploitation.objects.filter(pk=self.pk).first()
            if original:
                if self.taux_mouvement is not None and self.taux_mouvement != original.taux_mouvement:
                    raise ValidationError("Le taux de mouvement historique ne peut pas être modifié.")
                if self.valeur_usd is not None and self.valeur_usd != original.valeur_usd:
                    raise ValidationError("La valeur USD historique ne peut pas être modifiée.")
        return super().clean()


class MouvementCaisseChargesPersonnelles(models.Model):
    mouvement_caisse = models.ForeignKey(MouvementCaisse, on_delete=models.CASCADE, related_name='mouvements_caisse_cp')
    sous_rubrique = models.ForeignKey(SousRubriqueCaisse, on_delete=models.CASCADE, related_name='sous_rubrique_cp')
    valeur_usd = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True,
                                     help_text="Valeur USD historique de la charge")
    taux_mouvement = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True,
                                         help_text="Taux historique au moment de la charge")
    objects = models.Manager()

    def save(self, *args, **kwargs):
        from decimal import Decimal
        from parametres.models import get_taux_usd_cdf

        creating = self.pk is None
        if creating:
            if self.taux_mouvement is None:
                date_m = None
                if self.mouvement_caisse and self.mouvement_caisse.date_mouvement:
                    date_m = self.mouvement_caisse.date_mouvement.date()
                self.taux_mouvement = get_taux_usd_cdf(date_m)
            if self.valeur_usd is None and self.mouvement_caisse:
                montant_fc = Decimal(str(self.mouvement_caisse.montant))
                self.valeur_usd = montant_fc / self.taux_mouvement if self.taux_mouvement else Decimal('0')
        else:
            original = MouvementCaisseChargesPersonnelles.objects.filter(pk=self.pk).first()
            if original:
                self.taux_mouvement = original.taux_mouvement
                self.valeur_usd = original.valeur_usd
        super().save(*args, **kwargs)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.pk:
            original = MouvementCaisseChargesPersonnelles.objects.filter(pk=self.pk).first()
            if original:
                if self.taux_mouvement is not None and self.taux_mouvement != original.taux_mouvement:
                    raise ValidationError("Le taux de mouvement historique ne peut pas être modifié.")
                if self.valeur_usd is not None and self.valeur_usd != original.valeur_usd:
                    raise ValidationError("La valeur USD historique ne peut pas être modifiée.")
        return super().clean()


class DemandeDecaissement(models.Model):
    EN_ATTENTE = 'EN_ATTENTE'
    APPROUVEE = 'APPROUVEE'
    REFUSEE = 'REFUSEE'
    EXECUTEE = 'EXECUTEE'

    STATUT_CHOICES = [
        (EN_ATTENTE, 'En attente de validation Direction'),
        (APPROUVEE, 'Approuvée (prête pour exécution caissier)'),
        (REFUSEE, 'Refusée'),
        (EXECUTEE, 'Exécutée (sortie effectuée)'),
    ]

    caisse = models.ForeignKey(CaisseCourante, on_delete=models.CASCADE, related_name='demandes_decaissement')
    demandeur = models.ForeignKey('users.CustomUser', on_delete=models.SET_NULL, null=True, related_name='decaissements_demandes')
    date_demande = models.DateTimeField(auto_now_add=True)
    montant = models.DecimalField(max_digits=18, decimal_places=2, help_text="Montant demandé par le caissier")
    montant_approuve = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, help_text="Montant validé par l'administrateur")
    rubrique = models.ForeignKey(RubriqueCaisse, on_delete=models.PROTECT, related_name='demandes_decaissement')
    sous_rubrique = models.ForeignKey(SousRubriqueCaisse, on_delete=models.PROTECT, null=True, blank=True)
    caisse_destination = models.ForeignKey('Caisse', on_delete=models.SET_NULL, null=True, blank=True, related_name='transferts_demandes')
    fournisseur = models.ForeignKey('fournisseurs.Fournisseur', on_delete=models.SET_NULL, null=True, blank=True)
    client = models.ForeignKey('clients.Client', on_delete=models.SET_NULL, null=True, blank=True)
    creancier = models.ForeignKey('creanciers.Creancier', on_delete=models.SET_NULL, null=True, blank=True)
    debiteur = models.ForeignKey('creanciers.Debiteur', on_delete=models.SET_NULL, null=True, blank=True)
    agent = models.ForeignKey('paie.Agent', on_delete=models.SET_NULL, null=True, blank=True)
    motif = models.CharField(max_length=255)
    reference = models.CharField(max_length=100, blank=True, null=True)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default=EN_ATTENTE)
    valide_par = models.ForeignKey('users.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='decaissements_approuves')
    date_decision = models.DateTimeField(null=True, blank=True)
    commentaire_decision = models.TextField(blank=True, null=True)
    mouvement_caisse = models.OneToOneField('MouvementCaisse', on_delete=models.SET_NULL, null=True, blank=True, related_name='demande_source')
    date_execution = models.DateTimeField(null=True, blank=True)
    objects = models.Manager()

    class Meta:
        ordering = ['-date_demande']
        verbose_name = 'Demande de décaissement'
        verbose_name_plural = 'Demandes de décaissement'

    def __str__(self):
        return f"Décaissement #{self.id} — {self.montant} FC ({self.get_statut_display()})"

    @property
    def est_en_attente(self):
        return self.statut == self.EN_ATTENTE

    @property
    def est_approuvee(self):
        return self.statut == self.APPROUVEE

    @property
    def est_executee(self):
        return self.statut == self.EXECUTEE

    @property
    def est_refusee(self):
        return self.statut == self.REFUSEE

    @property
    def montant_final(self):
        return self.montant_approuve if self.montant_approuve is not None else self.montant