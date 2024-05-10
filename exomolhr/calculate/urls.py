from django.urls import path
from django.urls import re_path, include


from . import views

app_name = 'calculate'
urlpatterns = [
    path('', views.get_calculate_params, name='get_calculate_params'),
    path('get-data/', views.get_data, name='get_data'),
    path('get-data/ajax-data/', views.ajax_data, name='ajax_data'),
]
