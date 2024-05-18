from django.db import models
from chem.models import Isotopologue
from django.conf import settings

import numpy as np


class HRMeta(models.Model):
    isotopologue = models.ForeignKey(Isotopologue, on_delete=models.CASCADE)
    QNs = models.TextField()
    data_filename = models.CharField(max_length=72)

    class Meta:
        app_label = "linelist"

    def __str__(self):
        return self.data_filename

    def get_Q(self, T):
        """Return the partition function at temperature T (K)."""

        # Lop off the molecule from the start of the data_filename and add
        # the extension .pf.
        pf_file = "__".join(f for f in self.data_filename.split("__")[1:]) + ".pf"
        pf_path = settings.DATA_DIR / pf_file
        Tgrid, Qgrid = np.loadtxt(pf_path, unpack=True)
        if T < 0 or T > Qgrid[-1]:
            raise ValueError(
                f"T={T} K out of range for partition function file {pf_file}."
            )
        return np.interp([T], Tgrid, Qgrid)
