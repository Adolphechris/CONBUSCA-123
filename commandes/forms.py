from django import forms

from produits.models import Article
from utils.custom_field import ArticleChoiceField, ArticleSelectWidget

from .models import Commande, DetailsCommande


class CommandeCreateForm(forms.ModelForm):
    class Meta:
        model = Commande
        exclude = ['numero', 'actif', 'cree_par', 'modifie_par', 'valide_par', 'date_validation', 'commentaire_decision', 'statut']
        widgets = {
            'date_commande': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'fournisseur': forms.Select(attrs={'class': 'form-control js-simple-select'}),
            'devise': forms.Select(attrs={'class': 'form-control js-simple-select'}),
            'taux': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fournisseur'].required = False
        self.fields['fournisseur'].empty_label = "--- Multi-fournisseurs (interne) ---"


class ArticleCommandeAddForm(forms.ModelForm):
    article = ArticleChoiceField(
        queryset=Article.objects.none(),
        empty_label="--- Sélectionner un article ---",
        widget=ArticleSelectWidget(
            attrs={'class': 'form-control js-simple-select', 'id': 'id_article_commande'}
        ),
    )

    class Meta:
        model = DetailsCommande
        fields = ['article', 'qte', 'prix']
        widgets = {
            'qte': forms.NumberInput(attrs={'class': 'form-control'}),
            'prix': forms.NumberInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['article'].queryset = (
            Article.objects.with_stock().filter(actif=True).order_by('designation')
        )
        self.fields['prix'].required = False
        self.fields['prix'].initial = 0


class ArticleCommandeUpdateForm(forms.ModelForm):
    article = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'disabled': True}),
        required=False,
    )

    class Meta:
        model = DetailsCommande
        fields = ['qte', 'prix']
        widgets = {
            'qte': forms.NumberInput(attrs={'class': 'form-control'}),
            'prix': forms.NumberInput(attrs={'class': 'form-control'}),
        }

    field_order = ['article', 'qte', 'prix']

    def __init__(self, *args, **kwargs):
        self.article = kwargs.pop('article', None)
        super().__init__(*args, **kwargs)
        self.fields['article'].initial = self.article
        self.fields['article'].widget.attrs['readonly'] = True
