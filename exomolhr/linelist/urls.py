from django.urls import path

from . import views

app_name = "linelist"
urlpatterns = [
    path("", views.get_linelist, name="get_linelist"),
    path("get-data/", views.get_data, name="get_data"),
    path("get-data/ajax-data", views.ajax_data, name="ajax_data"),
    path("get-data/download/", views.download_archive, name="download_archive"),
]
