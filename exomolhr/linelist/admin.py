from django.contrib import admin
from .models import HRMeta

class HRMetaAdmin(admin.ModelAdmin):
    pass
admin.site.register(HRMeta, HRMetaAdmin)
