from django.db import models
import os
import struct
from pyvalem.formula import Formula


class Molecule(models.Model):
    stoichiometric_formula = models.CharField(max_length=40)
    ordinary_formula = models.CharField(max_length=80, unique=True)
    html = models.CharField(max_length=256)
    mass = models.FloatField()
    charge = models.SmallIntegerField()
    inchi = models.CharField(max_length=200, blank=True)
    inchikey = models.CharField(max_length=27, blank=True)
    cml = models.TextField(null=True, blank=True)
    slug = models.CharField(max_length=80, unique=True)
    names = models.CharField(max_length=2000, blank=True)

    def __str__(self):
        return self.ordinary_formula

    class Meta:
        app_label = "chem"


class Isotopologue(models.Model):
    stoichiometric_formula = models.CharField(max_length=80)
    ordinary_formula = models.CharField(max_length=160, unique=True)
    html = models.CharField(max_length=256)
    mass = models.FloatField()
    charge = models.SmallIntegerField()
    molecule = models.ForeignKey("Molecule", on_delete=models.CASCADE)
    inchi = models.CharField(max_length=200, blank=True)
    inchikey = models.CharField(max_length=27, blank=True)
    abundance = models.FloatField(null=True, blank=True)
    cml = models.TextField(null=True, blank=True)
    slug = models.CharField(max_length=160, unique=True)
    point_group = models.CharField(max_length=5, blank=True)

    def __str__(self):
        return self.ordinary_formula

    class Meta:
        app_label = "chem"
