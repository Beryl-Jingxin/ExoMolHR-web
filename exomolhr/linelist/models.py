from django.db import models
from chem.models import Isotopologue

class HRMeta(models.Model):
    isotopologue = models.ForeignKey(Isotopologue, on_delete=models.CASCADE)
    QNs = models.TextField()
    data_filename = models.CharField(max_length=72)

    class Meta:
        app_label = 'linelist'

    def __str__(self):
        return self.data_filename

    def get_Q(self, T):
        """Return the partition function at temperature T (K)."""
