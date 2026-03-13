from django.urls import path
from django.views.generic import RedirectView
from . import views

app_name = "linelist"
urlpatterns = [
    path("", views.home, name="home"),
    path("qn/", views.qnlabel, name="qnlabel"),
    path("about/", views.about, name="about"),
    path("citation/", views.citation, name="citation"),
    path("updates/", views.updates, name="updates"),
    path("db/", views.get_linelist, name="get_linelist"),
    path("db/<str:csv_filename>/", views.download_csv, name="download_csv"),
    path("pf/<str:pf_filename>/", views.view_pf, name="view_pf"),
    path("get-data/", views.get_data, name="get_data"),
    path("get-data/ajax-data", views.ajax_data, name="ajax_data"),
    path("get-data/download/", views.download_archive, name="download_archive"),
    path("exomolhr.all.json", RedirectView.as_view(url='/exomolhr/db/exomolhr.all.json')),
]
