from django.urls import path
from django.urls import re_path


from . import views

urlpatterns = [
    # path('', views.home.as_view()),
    # path('', views.home, name='home'),
    path('', views.molecule, name='molecule'),
    path('<str:molecule>', views.isotopologue, name='isotopologue'),
    path('<str:molecule>/<str:isotopologue>', views.dataset, name='dataset'),
    path('<str:molecule>/<str:isotopologue>/<str:dataset>', views.species, name='species'),
    path('download/<str:molecule>/<str:isotopologue>/<str:dataset>/', views.download_localfile, name='localcsv'),

    # path('search/', views.search, name='search'),
    # path('results/', views.results, name='results'),
    # path('download/', views.download, name='search_results_download'),
]