from django.contrib import admin
from .models import HRMeta


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


class HRMetaAdmin(admin.ModelAdmin):
    list_display = (
        "data_filename",
        "isotopologue",
        "numin",
        "numax",
        "created_at",
        "updated_at",
    )
    list_filter = (AdminSortFilter,)
    search_fields = (
        "data_filename",
        "isotopologue__ordinary_formula",
        "isotopologue__molecule__ordinary_formula",
    )
    readonly_fields = ("created_at", "updated_at")

    def get_ordering(self, request):
        sort_by = request.GET.get("sort_by")
        if sort_by == "created":
            return ("-created_at",)
        if sort_by == "updated":
            return ("-updated_at",)
        return ("data_filename",)


admin.site.register(HRMeta, HRMetaAdmin)
