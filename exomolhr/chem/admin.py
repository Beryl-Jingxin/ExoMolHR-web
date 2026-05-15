from django.contrib import admin
from chem.models import Molecule, Isotopologue


class AdminSortFilter(admin.SimpleListFilter):
    title = "sort by"
    parameter_name = "sort_by"

    def lookups(self, request, model_admin):
        return (
            ("alpha", "First letter"),
            ("created", "Created time"),
            ("updated", "Modified time"),
        )

    def queryset(self, request, queryset):
        return queryset


class SortableAdminMixin:
    alpha_ordering = ("ordinary_formula",)

    def get_ordering(self, request):
        sort_by = request.GET.get("sort_by")
        if sort_by == "created":
            return ("-created_at",)
        if sort_by == "updated":
            return ("-updated_at",)
        return self.alpha_ordering


class MoleculeAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = (
        "ordinary_formula",
        "names",
        "mass",
        "created_at",
        "updated_at",
    )
    list_filter = (AdminSortFilter,)
    search_fields = ("ordinary_formula", "names", "slug")
    readonly_fields = ("created_at", "updated_at")


admin.site.register(Molecule, MoleculeAdmin)


class IsotopologueAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = (
        "ordinary_formula",
        "molecule",
        "mass",
        "created_at",
        "updated_at",
    )
    list_filter = (AdminSortFilter,)
    search_fields = (
        "ordinary_formula",
        "molecule__ordinary_formula",
        "slug",
    )
    readonly_fields = ("created_at", "updated_at")


admin.site.register(Isotopologue, IsotopologueAdmin)
