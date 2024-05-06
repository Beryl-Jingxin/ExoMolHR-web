from enum import unique
from django.db import models
import os
from taggit.managers import TaggableManager
from pyvalem.formula import Formula, FormulaParseError
from pyqn.quantity import Quantity
from traitlets import default


class MoleculeError(Exception):
    pass


class StateError(Exception):
    pass


class TransitionError(Exception):
    pass


class Molecule(models.Model):
    """A data model representing a molecule of a stateless species, without regards to
    different isotopologues.
    It is highly recommended to only use the available class methods to interact with
    the database (get_from_* and create_from_*), as these are coded to handle the name
    canonicalization etc.
    """

    # The following fields should be compatible with ExoMol database itself (and the
    # formula_str needs to be compatible with pyvalem.formula.Formula)
    formula_str = models.CharField(max_length=16)
    name = models.CharField(max_length=64, default="")

    sync_functions = {
        "slug": lambda molecule: Formula(molecule.formula_str).slug,
        "html": lambda molecule: Formula(molecule.formula_str).html,
        "charge": lambda molecule: Formula(molecule.formula_str).charge,
        "number_atoms": lambda molecule: Formula(molecule.formula_str).natoms,
    }
    
    id = models.PositiveSmallIntegerField(primary_key=True)
    formula = models.CharField(max_length=30, unique=True, null=True)
    slug = models.CharField(max_length=80, unique=True, null=True, blank=True)
    name = models.CharField(max_length=100, unique=True, null=True, blank=True)
    mass = models.FloatField(null=True, blank=True)
    html = models.CharField(max_length=200, unique=True, null=True, blank=True)
    charge = models.SmallIntegerField(default=0, null=True, blank=True)
    number_atoms = models.PositiveSmallIntegerField()

    tags = TaggableManager()
    """
    The code defines a model for chemical molecules with methods to generate HTML representation of the
    formula and calculate the mass of the molecule.
    :return: The `formula_html` method returns the HTML representation of the chemical formula stored in
    the instance's `formula` attribute. If the formula can be successfully parsed using the `Formula`
    class, it returns the HTML representation of the formula. If there is a `FormulaParseError`, it
    returns the original formula string.
    """
    
    def __str__(self):
        return self.formula_str
    
    class Meta:
        db_table = 'chem_molecule'
        app_label = 'chem'
        
    def formula_html(self):
        try:
            formula_html = Formula(self.formula_str).html
        except FormulaParseError:
            formula_html = self.formula_str
        return formula_html
    
    def get_mass(self): 
        try:
            mass = Formula(self.formula_str).rmm
        except FormulaParseError:
            mass = self.mass
        return mass 

    @classmethod
    def get_from_formula_str(cls, formula_str):
        """The formula_str needs to be canonicalised formula compatible with
        pyvalem.formula.Formula argument.
        It is expected that only a single Molecule instance with a given formula_str
        exists, otherwise this might lead to inconsistent behaviour.
        """
        return cls.objects.get(formula_str=formula_str)

    @classmethod
    def create_from_data(cls, formula_str, name=""):
        """A method for creation of new Molecule instances. It is highly recommended to
        use this method to prevent multiple Molecule duplicates, inconsistent fields,
        etc.
        Example:
            formula_str = 'H2O',
            name = 'Water'
        The arguments should be compatible with ExoMol database itself.
        """
        pyvalem_formula = Formula(formula_str)

        # ensure the passed formula_str is canonicalised (canonicalisation offloaded to
        # pyvalem)
        if repr(pyvalem_formula) != formula_str:
            raise MoleculeError(
                f"Non-canonicalised formula {formula_str} passed, "
                f"instead of {repr(pyvalem_formula)}"
            )

        try:
            cls.get_from_formula_str(formula_str)
            # Only a single instance with the given formula_str should exist!
            raise MoleculeError(f"Molecule({formula_str}) already exists!")
        except cls.DoesNotExist:
            pass

        instance = cls(formula_str=formula_str, name=name)
        instance.sync()
        return instance        
    
    
class Isotopologue(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True)
    molecule = models.ForeignKey('Molecule', on_delete=models.CASCADE, null=True)
    formula = models.CharField(max_length=30, unique=True, null=True)
    slug = models.CharField(max_length=80, unique=True, null=True, blank=True)
    dataset = models.CharField(max_length=200, unique=True, null=True)
    abundance =  models.FloatField(default=1, null=True, blank=True)
    mass = models.FloatField(null=True, blank=True)
    html = models.CharField(max_length=200, unique=True, blank=True)
    charge = models.SmallIntegerField(default=0, null=True, blank=True)
    
    def __str__(self):
        return self.formula   
    
    class Meta:
        db_table = 'chem_isotopologue'
        app_label = 'chem'

    def formula_html(self):
        try:
            formula_html = Formula(self.formula).html
        except FormulaParseError:
            formula_html = self.formula
        return formula_html
    
    def get_mass(self): 
        try:
            mass = Formula(self.formula).rmm
        except FormulaParseError:
            mass = self.mass
        return mass  
    