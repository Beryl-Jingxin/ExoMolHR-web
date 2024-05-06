import json
from django.db import models

from chem.models import Molecule, Isotopologue

# Create your models here.

class Linelists(models.Model):
    # Molecule, isotopologue and dataset names.
    isotopologue = models.ForeignKey(Isotopologue, on_delete=models.CASCADE, null=True)

    # The transition wavenumber, in cm-1.
    nu = models.FloatField()
    
    # Uncertainty.
    unc = models.FloatField()
    
    # The transition Einstein A-coefficient, in s-1.
    A = models.FloatField()
    
    # The transition intensity in cm-1/(molec.cm-2), weighted by isotopologue
    # abundance.
    S = models.FloatField()

    # Lower-state energy, in cm-1.
    Epp = models.FloatField()

    # The upper and lower state degeneracies, including any nuclear spin factors.
    gp = models.PositiveSmallIntegerField()
    gpp = models.PositiveSmallIntegerField()
    
    # The upper and lower state total angular momentum.
    Jp = models.PositiveSmallIntegerField(null=True)
    Jpp = models.PositiveSmallIntegerField(null=True)

    # Quantumn numbers of upper and lower state.
    qnp = models.CharField(max_length=500)
    qnpp = models.CharField(max_length=500)

    prms_json = models.TextField(null=True)


    def __str__(self):
        return f'{self.isotopologue.text}: {self.nu} cm-1'

    def to_csv(self):
        return ', '.join([str(e) for e in (self.isotopologue.text, self.nu, self.unc,
                                           self.A, self.S, self.Epp, self.gp, self.gpp,
                                           self.Jp, self.Jpp, self.qnp, self.qnpp)])

    def to_json(self):
        return json.dumps({'nu': self.nu, 'unc': self.unc, 'A': self.A, 'S': self.S,
                           'Epp': self.Epp, 'gp': self.gp, 'gpp': self.gpp, 'Jp': self.Jp,
                           'Jpp': self.Jpp, 'qnp': self.qnp, 'qnpp': self.qnpp})


# class Molecule(models.Model):
#     formula = models.CharField('Molecule', max_length=16)
    
#     def __str__(self):
#         return self.formula
 

# class Molecule(models.Model):
#     mid = models.PositiveSmallIntegerField(primary_key=True)
#     formula = models.CharField('Molecule', max_length=16, null=True)
#     name = models.CharField('MolName', max_length=64, unique=True, null=True)
    
#     html = models.CharField(max_length=200, unique=True, null=True)
#     charge = models.SmallIntegerField(default=0, null=True)
#     slug = models.CharField(max_length=80, unique=True, null=True)
    
#     tags = TaggableManager()
    
#     def __str__(self):
#         return self.formula
    
    
# class Isotopologue(models.Model):
#     iid = models.PositiveSmallIntegerField(primary_key=True)
#     iso_slug = models.CharField(max_length=80, unique=True, null=True)
    
#     molecule = models.ForeignKey(Molecule, on_delete=models.CASCADE)
    
#     # text = models.CharField(max_length=80, unique=True)
#     # html = models.CharField(max_length=200, unique=True)
#     # charge = models.SmallIntegerField(default=0, null=True)
#     # slug = models.CharField(max_length=80, unique=True)
    
#     def __str__(self):
#         return self.iid
    
class MoleculeTables(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True)
    molecule = models.ForeignKey(Molecule, on_delete=models.CASCADE, blank=True)
    name = models.CharField(max_length=100)
    
    def __str__(self):
        return self.molecule.text
    
    def to_csv(self):
        return ', '.join([str(e) for e in (self.id, self.molecule.text, self.name)])
    
    


    

