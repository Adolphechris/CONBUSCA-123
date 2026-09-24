from django.urls import path
from .views import (
    DirectionCockpitView,
    DirectionCommandeValiderView,
    DirectionCommandeRefuserView,
    DirectionDecaissementApprouverView,
    DirectionDecaissementRefuserView,
    DirectionUsersView,
    DirectionUserToggleActiveView,
    DirectionUserResetPasswordView,
    DirectionLogsView,
)

urlpatterns = [
    path('', DirectionCockpitView.as_view(), name='direction_cockpit'),
    # Commandes
    path('commande/<int:pk>/valider', DirectionCommandeValiderView.as_view(), name='direction_commande_valider'),
    path('commande/<int:pk>/refuser', DirectionCommandeRefuserView.as_view(), name='direction_commande_refuser'),
    # Décaissements
    path('decaissement/<int:pk>/approuver', DirectionDecaissementApprouverView.as_view(), name='direction_decaissement_approuver'),
    path('decaissement/<int:pk>/refuser', DirectionDecaissementRefuserView.as_view(), name='direction_decaissement_refuser'),
    # Gestion utilisateurs
    path('users/', DirectionUsersView.as_view(), name='direction_users'),
    path('users/<int:pk>/toggle-active', DirectionUserToggleActiveView.as_view(), name='direction_user_toggle'),
    path('users/<int:pk>/reset-password', DirectionUserResetPasswordView.as_view(), name='direction_user_reset_password'),
    # Logs
    path('logs/', DirectionLogsView.as_view(), name='direction_logs'),
]
