from django.urls import include, path

from . import views

urlpatterns = [    
    path('', views.molecule, name='molecule'),
    path('<str:molecule>', views.isotopologue, name='isotopologue'),
    path('<str:molecule>/<str:isotopologue>', views.dataset, name='dataset'),
    path('<str:molecule>/<str:isotopologue>/<str:dataset>', views.species, name='species'),
    path('<str:molecule>/<str:isotopologue>/<str:dataset>/download/', views.download_localfile, name='localcsv'),
    
]