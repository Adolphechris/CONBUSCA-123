from django.db import models
from django.conf import settings
from django.utils import timezone


class NotificationInterne(models.Model):
    INFO = 'INFO'
    VALIDATION = 'VALIDATION'
    REFUS = 'REFUS'
    URGENT = 'URGENT'

    TYPE_CHOICES = [
        (INFO, 'Information'),
        (VALIDATION, 'Validation / Approbation'),
        (REFUS, 'Refus / Rejet'),
        (URGENT, 'Alerte Urgente'),
    ]

    destinataire = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications_recues',
    )
    emetteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications_emises',
    )
    titre = models.CharField(max_length=150)
    message = models.TextField()
    type_notification = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default=INFO,
    )
    lien = models.CharField(max_length=255, blank=True, null=True)
    lu = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_lecture = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-date_creation']
        indexes = [
            models.Index(fields=['destinataire', 'lu', '-date_creation']),
        ]
        verbose_name = 'Notification interne'
        verbose_name_plural = 'Notifications internes'

    def __str__(self):
        return f'[{self.type_notification}] {self.titre} -> {self.destinataire}'

    def marquer_comme_lu(self):
        if not self.lu:
            self.lu = True
            self.date_lecture = timezone.now()
            self.save(update_fields=['lu', 'date_lecture'])

    @classmethod
    def notifier(cls, destinataire, titre, message, type_notification=INFO, lien=None, emetteur=None):
        return cls.objects.create(
            destinataire=destinataire,
            emetteur=emetteur,
            titre=titre,
            message=message,
            type_notification=type_notification,
            lien=lien,
        )

    @classmethod
    def notifier_superadmins(cls, titre, message, type_notification=INFO, lien=None, emetteur=None):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        admins = User.objects.filter(is_superuser=True, is_active=True)
        notifs = []
        for admin in admins:
            notifs.append(cls(
                destinataire=admin,
                emetteur=emetteur,
                titre=titre,
                message=message,
                type_notification=type_notification,
                lien=lien,
            ))
        if notifs:
            cls.objects.bulk_create(notifs)
        return notifs
