from django.urls import path
from .views import (
    CaisseView, CaissesView, OuvertureCaisseView, HistoriqueCaisseView,
    MouvementCaisseDeleteView, get_update_caisse_form, rubrique_champ_view,
    ClotureCaisseView,
    DemandeDecaissementCreateView,
    DemandeDecaissementExecuterView,
    DemandesDecaissementListView,
    DemandeDecaissementPdfView,
)

urlpatterns = [
    path('caisses', CaissesView.as_view(), name='caisses'),
    path('<int:pk>/historique', HistoriqueCaisseView.as_view(), name='historique_caisse'),
    path('ouverture', OuvertureCaisseView.as_view(), name='ouverture_caisse'),
    path('<int:pk>/ouverture', OuvertureCaisseView.as_view(), name='ouverture_caisse'),
    path('<int:pk>', CaisseView.as_view(), name='caisse_details'),
    path('update_caisse_form/<int:pk>/', get_update_caisse_form, name='get_form_caisse_update'),
    path('<int:caisse_pk>/delete_mouvement/<int:pk>/', MouvementCaisseDeleteView.as_view(), name='delete_mouvement_caisse'),
    path('<int:caisse_pk>/rubrique_champ/', rubrique_champ_view, name='rubrique_champ'),
    path('<int:pk>/cloture', ClotureCaisseView.as_view(), name='cloture_caisse'),
    # Circuit décaissement
    path('<int:pk>/decaissement/nouveau', DemandeDecaissementCreateView.as_view(), name='decaissement_nouveau'),
    path('decaissement/<int:pk>/executer', DemandeDecaissementExecuterView.as_view(), name='decaissement_executer'),
    path('decaissement/<int:pk>/manifeste-pdf', DemandeDecaissementPdfView.as_view(), name='decaissement_manifeste_pdf'),
    path('<int:pk>/decaissements', DemandesDecaissementListView.as_view(), name='decaissements_list'),
]