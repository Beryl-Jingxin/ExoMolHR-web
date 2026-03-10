from django.contrib import admin
from chem.models import Molecule, Isotopologue


class MoleculeAdmin(admin.ModelAdmin):
    pass


admin.site.register(Molecule, MoleculeAdmin)


class IsotopologueAdmin(admin.ModelAdmin):
    search_fields = [
        "ordinary_formula",
    ]
    pass


admin.site.register(Isotopologue, IsotopologueAdmin)
