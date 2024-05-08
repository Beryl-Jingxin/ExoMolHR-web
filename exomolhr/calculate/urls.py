from django.urls import path
from django.urls import re_path, include


from . import views

urlpatterns = [
    path('', views.get_calculate_params, name='get_calculate_params'),
    path('get-data/', views.get_data, name='get_data'),
]
