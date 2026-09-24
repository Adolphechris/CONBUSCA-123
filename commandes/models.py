from django.db import models
from django.urls import reverse


class Commande(models.Model):
    BROUILLON = 'BROUILLON'
    EN_ATTENTE = 'EN_ATTENTE'
    VALIDEE = 'VALIDEE'
    REFUSEE = 'REFUSEE'
    TRANSFORMEE = 'TRANSFORMEE'
    
    STATUT_CHOICES = [
        (BROUILLON, 'Brouillon'),
        (EN_ATTENTE, 'En attente de validation'),
        (VALIDEE, 'Validée'),
        (REFUSEE, 'Refusée'),
        (TRANSFORMEE, 'Transformée'),
    ]
    
    numero = models.IntegerField(unique=True, blank=False)
    date_commande = models.DateField()
    fournisseur = models.ForeignKey(
        'fournisseurs.Fournisseur',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Fournisseur principal ou vide si commande multi-fournisseurs",
    )
    devise = models.ForeignKey(
        'parametres.Devise',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name='Devise',
    )
    taux = models.DecimalField(default=0, max_digits=12, decimal_places=4)
    statut = models.CharField(
        max_length=25,
        choices=STATUT_CHOICES,
        default=BROUILLON,
        verbose_name='Statut'
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    date_validation = models.DateTimeField(null=True, blank=True)
    valide_par = models.ForeignKey(
        'users.CustomUser',
        related_name='commandes_validees',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    commentaire_decision = models.TextField(
        blank=True,
        null=True,
        help_text="Motif de refus ou observation de la Direction",
    )
    cree_par = models.ForeignKey(
        'users.CustomUser',
        related_name='commandecreepar',
        on_delete=models.PROTECT,
    )
    modifie_par = models.ForeignKey(
        'users.CustomUser',
        related_name='commandemodpar',
        on_delete=models.PROTECT,
        blank=True,
        null=True,
    )
    actif = models.BooleanField(default=True)

    objects = models.Manager()

    class Meta:
        ordering = ['-numero']
        verbose_name = 'Commande'
        verbose_name_plural = 'Commandes'

    def __str__(self) -> str:
        return str(self.numero)

    def get_absolute_url(self) -> str:
        return reverse('commande_details', args=[self.pk])

    @property
    def est_modifiable(self) -> bool:
        """Une commande validée ou refusée par la Direction ne peut plus être modifiée par l'utilisateur."""
        return self.statut in (self.BROUILLON, self.EN_ATTENTE)


class DetailsCommande(models.Model):
    commande = models.ForeignKey(Commande, on_delete=models.PROTECT)
    article = models.ForeignKey(
        'produits.Article',
        on_delete=models.PROTECT,
        null=True,
    )
    qte = models.IntegerField()
    prix = models.DecimalField(max_digits=12, decimal_places=2)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    objects = models.Manager()

    class Meta:
        verbose_name = 'Détail commande'
        verbose_name_plural = 'Détails commande'

    def __str__(self) -> str:
        return f"{self.commande} – {self.article}"

    @property
    def prix_total(self) -> float:
        # Calcul pur, sans requête DB — autorisé en @property
        return self.qte * self.prix

    def get_absolute_url(self) -> str:
        return reverse('commande_details', args=[self.commande.pk])
