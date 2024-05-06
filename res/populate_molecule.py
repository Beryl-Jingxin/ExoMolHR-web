import os
import sys

from conf import exomolhr_root
sys.path.append(exomolhr_root)
os.environ['DJANGO_SETTINGS_MODULE'] = 'exomolhr.settings'

# Prepare the Django models
import django
django.setup()

from pyvalem.formula import Formula

from chem.models import Molecule, Isotopologue


for line in open('molecules.csv'):
    fields = line.split(',')
    id = int(fields[0])
    formula = fields[1].strip()
    name = fields[2]

    pyvalem_formula = Formula(formula)
    formula_can = repr(pyvalem_formula)
    assert formula == formula_can

    try:
        molecule = Molecule.objects.get(formula=formula)
        print(f'{molecule} already in the database!')
        continue
    except Molecule.DoesNotExist:
        pass

    # molecule = Molecule(id=id, formula=formula, name=name, 
    #                     slug=pyvalem_formula.slug, html=pyvalem_formula.html,
    #                     mass=pyvalem_formula.rmm, charge=pyvalem_formula.charge)
    
    molecule = Molecule(id=id, formula=formula, slug=pyvalem_formula.slug, 
                        name=name, mass=pyvalem_formula.rmm)
    molecule.save()
    assert molecule.id == id

for line in open('isotopologues.csv'):
    fields = line.split(',')
    id = int(fields[0])
    molecule = fields[1].strip()
    slug = fields[2].strip()
    formula = fields[3].strip()

    molecule = Molecule.objects.get(formula=molecule)
    
    pyvalem_formula = Formula(formula)
    formula_can = repr(pyvalem_formula)
    assert formula == formula_can

    print(pyvalem_formula.html)
    print(pyvalem_formula.slug)
    print(molecule)

    try:
        isotopologue = Isotopologue.objects.get(formula=formula)
        print(f'{isotopologue} already in the database!')
        continue
    except Isotopologue.DoesNotExist:
        pass

    isotopologue = Isotopologue(id=id, molecule=molecule, formula=formula,
                                slug=pyvalem_formula.slug, mass=pyvalem_formula.rmm 
                                )
    isotopologue.save()
    assert isotopologue.id == id
