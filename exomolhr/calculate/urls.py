from django.urls import path
from django.urls import re_path, include


from . import views

urlpatterns = [
    path('', views.molecules, name='molecules'),
    re_path(r'^(?P<molecules_url>[\w_]+)/(?P<isotopologues_url>[\w\d\0-9]+)/(?P<datasets_url>[\w_]+)/$', views.dofilters, name='dofilters'),
    re_path(r'^(?P<molecules_url>[\w_]+)/(?P<isotopologues_url>[\w\d\0-9]+)/$', views.datasets, name='datasets'),
    re_path(r'^(?P<molecules_url>[\w_]+)/$', views.isotopologues, name='isotopologues'),
    
    
    
    # path('<str:molecule>/<str:isotopologue>/<str:dataset>', views.filters, name='filters'),
    # path('download/<str:molecule>/<str:isotopologue>/<str:dataset>/', views.download_localfile, name='localcsv'),

    # path('search/', views.search, name='search'),
    # path('results/', views.results, name='results'),
    # path('download/', views.download, name='search_results_download'),
]
