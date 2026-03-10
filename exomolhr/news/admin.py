from django.contrib import admin
from django import forms
import datetime
from .models import SiteUpdate


class SiteUpdateForm(forms.ModelForm):
    class Meta:
        model = SiteUpdate
        fields = '__all__'
        widgets = {
            'date': forms.SelectDateWidget(years=range(2020, datetime.date.today().year + 10))
        }

class SiteUpdateAdmin(admin.ModelAdmin):
    form = SiteUpdateForm
    list_display = ("id", "formatted_date", "title", "is_highlighted")
    list_editable = ("is_highlighted",)
    ordering = ("date", "id")

    @admin.display(description='Date', ordering='date')
    def formatted_date(self, obj):
        return obj.date.strftime('%d %b %Y')


admin.site.register(SiteUpdate, SiteUpdateAdmin)
