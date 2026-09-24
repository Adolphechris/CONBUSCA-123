from django.urls import path
from .views import (
    NotificationsListView,
    MarquerNotificationLueView,
    MarquerToutesLuesView,
    NotificationBadgeView,
)

urlpatterns = [
    path('', NotificationsListView.as_view(), name='notifications_list'),
    path('<int:pk>/lire/', MarquerNotificationLueView.as_view(), name='notification_lire'),
    path('tout-lire/', MarquerToutesLuesView.as_view(), name='notifications_tout_lire'),
    path('badge/', NotificationBadgeView.as_view(), name='notifications_badge'),
]
