from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import ListView

from .models import NotificationInterne


class NotificationsListView(LoginRequiredMixin, ListView):
    model = NotificationInterne
    template_name = 'notifications/notifications_list.html'
    context_object_name = 'notifications'
    paginate_by = 20

    def get_queryset(self):
        filtre = self.request.GET.get('filtre', 'toutes')
        qs = NotificationInterne.objects.filter(destinataire=self.request.user)
        if filtre == 'non_lues':
            qs = qs.filter(lu=False)
        return qs.select_related('emetteur')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filtre_actif'] = self.request.GET.get('filtre', 'toutes')
        ctx['nb_non_lues'] = NotificationInterne.objects.filter(destinataire=self.request.user, lu=False).count()
        return ctx


class MarquerNotificationLueView(LoginRequiredMixin, View):
    def post(self, request, pk):
        notif = get_object_or_404(NotificationInterne, pk=pk, destinataire=request.user)
        notif.marquer_comme_lu()
        if request.headers.get('HX-Request') == 'true':
            return HttpResponse('<span class="badge bg-secondary">Lu</span>')
        return redirect(notif.lien or reverse('notifications_list'))


class MarquerToutesLuesView(LoginRequiredMixin, View):
    def post(self, request):
        NotificationInterne.objects.filter(destinataire=request.user, lu=False).update(
            lu=True,
            date_lecture=timezone.now(),
        )
        if request.headers.get('HX-Request') == 'true':
            return HttpResponse('<span class="badge bg-success">Toutes lues</span>')
        return redirect('notifications_list')


class NotificationBadgeView(LoginRequiredMixin, View):
    def get(self, request):
        non_lues = NotificationInterne.objects.filter(destinataire=request.user, lu=False)
        count = non_lues.count()
        recents = non_lues.select_related('emetteur')[:5]
        return render(request, 'notifications/partials/navbar_bell.html', {
            'count': count,
            'recents': recents,
        })
