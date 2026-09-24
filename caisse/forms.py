from django import forms
from .models import MouvementCaisse, RubriqueCaisse
from django.urls import reverse

class OuvertureCaisseValidateForm(forms.Form):
    pass

class ClotureCaisseValidateForm(forms.Form):
    pass


class CaisseForm(forms.ModelForm):
    class Meta:
        model = MouvementCaisse
        fields = ['type_mouvement', 'rubrique', 'montant', 'motif']
        widgets = {
            'type_mouvement': forms.Select(attrs={'class': 'form-control js-simple-select'}),
            'rubrique': forms.Select(attrs={'class': 'form-control'}),
            'montant': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Montant'}),
            'motif': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Motif *'}),
        }
        labels = {
            'motif': 'Motif *',
        }


    def __init__(self, *args, **kwargs):
        # PK CaisseCourante (session ouverte), requis par rubrique_champ_view.
        self.caisse_pk = kwargs.pop('caisse_pk', None)
        super().__init__(*args, **kwargs)
        self.fields['rubrique'].queryset = RubriqueCaisse.objects.filter(visible=True)
        # Motif obligatoire pour toute opération
        self.fields['motif'].required = True
        # In edit mode the server pre-renders the correct dependent field, so we
        # must NOT fire 'load' (it would overwrite the pre-filled content with the
        # first item in the list). Only listen to explicit user changes.
        editing = bool(self.instance and self.instance.pk)
        trigger = 'change' if editing else 'load, change'
        self.fields['rubrique'].widget.attrs.update({
            'hx-get': reverse('rubrique_champ', kwargs={'caisse_pk': self.caisse_pk}),
            'hx-target': 'next .rubrique-dependent-fields',
            'hx-trigger': trigger,
        })


# ── Formulaire demande de décaissement ──────────────────────────────────────

class DemandeDecaissementForm(forms.Form):
    """
    Formulaire de soumission d'une demande de décaissement par le caissier.
    RÈGLE : Ce formulaire ne crée PAS de MouvementCaisse.
    Il crée seulement une DemandeDecaissement EN_ATTENTE.
    """
    montant = forms.DecimalField(
        max_digits=18,
        decimal_places=2,
        min_value=1,
        label="Montant demandé (FC)",
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ex: 50000',
            'step': '1',
        }),
    )
    rubrique = forms.ModelChoiceField(
        queryset=RubriqueCaisse.objects.filter(visible=True),
        label="Rubrique",
        widget=forms.Select(attrs={'class': 'form-control select2'}),
    )
    sous_rubrique = forms.ModelChoiceField(
        queryset=__import__('caisse.models', fromlist=['SousRubriqueCaisse']).SousRubriqueCaisse.objects.all(),
        required=False,
        label="Sous-rubrique (optionnel)",
        widget=forms.Select(attrs={'class': 'form-control select2'}),
    )
    motif = forms.CharField(
        max_length=255,
        label="Motif / Objet du décaissement",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ex: Achat fournitures bureau, règlement loyer...',
        }),
    )
    reference = forms.CharField(
        max_length=100,
        required=False,
        label="Référence (facture, bon, N° dossier...)",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Optionnel',
        }),
    )

    # Tiers (tous optionnels — à remplir selon la rubrique)
    fournisseur = forms.ModelChoiceField(
        queryset=__import__('fournisseurs.models', fromlist=['Fournisseur']).Fournisseur.objects.filter(actif=True) if hasattr(__import__('fournisseurs.models', fromlist=['Fournisseur']).Fournisseur, 'actif') else __import__('fournisseurs.models', fromlist=['Fournisseur']).Fournisseur.objects.all(),
        required=False,
        label="Fournisseur concerné",
        widget=forms.Select(attrs={'class': 'form-control select2'}),
    )
    client = forms.ModelChoiceField(
        queryset=__import__('clients.models', fromlist=['Client']).Client.objects.all(),
        required=False,
        label="Client concerné",
        widget=forms.Select(attrs={'class': 'form-control select2'}),
    )
    creancier = forms.ModelChoiceField(
        queryset=__import__('creanciers.models', fromlist=['Creancier']).Creancier.objects.all(),
        required=False,
        label="Créancier concerné",
        widget=forms.Select(attrs={'class': 'form-control select2'}),
    )
    agent = forms.ModelChoiceField(
        queryset=__import__('paie.models', fromlist=['Agent']).Agent.objects.all(),
        required=False,
        label="Agent concerné",
        widget=forms.Select(attrs={'class': 'form-control select2'}),
    )

    def __init__(self, *args, **kwargs):
        self.caisse_pk = kwargs.pop('caisse_pk', None)
        super().__init__(*args, **kwargs)
        # Filtrer les rubriques SORTIE uniquement (les décaissements sont des sorties)
        self.fields['rubrique'].queryset = RubriqueCaisse.objects.filter(visible=True)

