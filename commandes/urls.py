from django.urls import path

from .views import (
    ArticleCommandeDeleteView,
    BonCommandePdfView,
    CommandeAutoSuggestView,
    CommandeCreateView,
    CommandeDeleteView,
    CommandeDetailView,
    CommandeGenererAutoView,
    CommandeLineCreateView,
    CommandeLineUpdateView,
    CommandeRefuserView,
    CommandeSaveView,
    CommandeSoumettreView,
    CommandeUpdateFormView,
    CommandeUpdateView,
    CommandeValiderView,
    CommandesView,
    ProformaPdfView,
)

urlpatterns = [
    path('', CommandesView.as_view(), name='commandes'),
    path('auto/', CommandeAutoSuggestView.as_view(), name='commande_auto_suggest'),
    path('auto/generer/', CommandeGenererAutoView.as_view(), name='commande_generer_auto'),
    path('commande/create', CommandeCreateView.as_view(), name='commande_create'),
    path('commande/<int:pk>', CommandeDetailView.as_view(), name='commande_details'),
    path('commande/update/<int:pk>', CommandeUpdateView.as_view(), name='commande_update'),
    path('commande/delete/<int:pk>', CommandeDeleteView.as_view(), name='commande_delete'),
    path('commande/save/<int:pk>', CommandeSaveView.as_view(), name='commande_save'),
    # HTMX lines
    path('commande/<int:pk>/lines/add', CommandeLineCreateView.as_view(), name='commande_line_add'),
    path('commande/<int:pk>/lines/update', CommandeLineUpdateView.as_view(), name='commande_line_update'),
    path('commande_update_form/<int:pk>/', CommandeUpdateFormView.as_view(), name='get_commande_update_form'),
    path('commande/<int:commande_pk>/delete_article/<int:pk>',
         ArticleCommandeDeleteView.as_view(), name='delete_article_commande'),
    # Workflow Direction
    path('commande/<int:pk>/soumettre', CommandeSoumettreView.as_view(), name='commande_soumettre'),
    path('commande/<int:pk>/valider', CommandeValiderView.as_view(), name='commande_valider'),
    path('commande/<int:pk>/refuser', CommandeRefuserView.as_view(), name='commande_refuser'),
    # PDF
    path('commande/<int:pk>/bon-commande', BonCommandePdfView.as_view(), name='bon_commande_pdf'),
    path('commande/<int:pk>/proforma', ProformaPdfView.as_view(), name='proforma_pdf'),
]
