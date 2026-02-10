"""
URL configuration for tests.
"""
from django.urls import path, include

urlpatterns = [
    path('', include('invoicing.urls')),
]

