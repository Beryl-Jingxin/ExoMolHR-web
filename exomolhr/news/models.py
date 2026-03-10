from django.db import models

class SiteUpdate(models.Model):
    date = models.DateField(help_text="The date of the update.")
    title = models.CharField(max_length=200, help_text="The title of the update.", default="Update")
    content = models.TextField(help_text="The update message.")
    is_highlighted = models.BooleanField(default=False, help_text="Mark this update as important to highlight it on the website.")

    class Meta:
        ordering = ["date", "id"]

    def __str__(self):
        return f"{self.date} - {self.title}"
