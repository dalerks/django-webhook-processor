from django.urls import path
from .views import EventListView, WebhookIngestView

urlpatterns = [
    path("webhooks/<str:source>/", WebhookIngestView.as_view()),
    path("events/", EventListView.as_view()),
]
