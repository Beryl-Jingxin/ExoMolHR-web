import django_filters

from .models import Linelist

#########################################################

class TransFilter(django_filters.FilterSet):

    numin = django_filters.NumberFilter(field_name='nu', lookup_expr='gte')
    numax = django_filters.NumberFilter(field_name='nu', lookup_expr='lt')

    molecule = django_filters.CharFilter(field_name='isotopologue__molecule__text',
                                         lookup_expr='exact')


    class Meta:
        model = Linelist
        fields = ('nu', 'isotopologue__molecule')
