############ All you need to modify is below ############
# Full path and name to your csv file
csv_filepathname="C:/Users/A/Documents/Projects/Django/sw2/wkw2/fixtures/data.csv"
# Full path to the directory immediately above your django project directory
your_djangoproject_home="C:.../Documents/PROJECTS/Django/"
############ All you need to modify is above ############
import csv
import sys,os
from conf import exomolhr_root
sys.path.append(exomolhr_root)
os.environ['DJANGO_SETTINGS_MODULE'] ='exomolhr.settings'

# from linelist.models import Molecule, IDMolecule

# dataReader = csv.reader(open('molecules.csv'), delimiter=',', quotechar='"')
# molecule_text = None
# for row in dataReader:
#     if molecule_text != row[1]:
#         molecule_text = row[1]
#         molecule = Molecule()
#         molecule.molecule_formula = molecule_text
#         molecule.save()

# dataReader = csv.reader(open('molecules.csv'), delimiter=',', quotechar='"')
# for row in dataReader:
#     id_mol_name = IDMolecule()
#     id_mol_name.id = row[0]
#     id_mol_name_molecule = Molecule.objects.get(molecule_formula=row[1])
#     id_mol_name.molecule = id_mol_name_molecule
#     id_mol_name.name = row[2]
#     id_mol_name.save()





# import csv, csv_to_sqlite 
# import sys,os
# from conf import exomolhr_root
# sys.path.append(exomolhr_root)
# os.environ['DJANGO_SETTINGS_MODULE'] ='exomolhr.settings'

# from chem.models import Molecule
# from pyvalem.formula import Formula


# with open('molecules.csv') as file:
#     dataReader = csv.reader(file, delimiter=',', quotechar='"')
    
#     id_mol = Molecule.objects.all().delete()

#     for row in dataReader:
#         formula=row[1]
#         pyvalem_formula = Formula(formula).html
#         id_mol = Molecule(mid=row[0], 
#                           formula=pyvalem_formula,
#                           name=row[2])
#         id_mol.save()
            
            
    # with open('molecules.csv') as file:
    #     dataReader = csv.reader(file, delimiter=',', quotechar='"')
        
    #     IDMolecule.objects.all().delete()
    #     MolIsotopologue.objects.all().delete()

    #     for row in dataReader:
    #         print(row)
            
    #         molformula, _ = IDMolecule.objects.get_or_create(formula=row[1])
    #         id_mol = IDMolecule(mid=row[0], 
    #                             molecule=molformula,
    #                             name=row[2])
    #         id_mol.save()
        



# import csv, sqlite3

# con = sqlite3.connect(":memory:") # change to 'sqlite:///your_filename.db'
# cur = con.cursor()
# cur.execute("CREATE TABLE t (ID, Molecule, MolName);") # use your column names here

# with open('molecules.csv','r') as fin: # `with` statement available in 2.5+
#     # csv.DictReader uses first line in file for column headings by default
#     dr = csv.DictReader(fin) # comma is default delimiter
#     to_db = [(i['ID'], i['Molecule'], i['MolName']) for i in dr]

# cur.executemany("INSERT INTO t (ID, Molecule, MolName) VALUES (?, ?, ?);", to_db)
# con.commit()
# con.close()


# options = csv_to_sqlite.CsvOptions(typing_style="full", encoding="windows-1250") 
# input_files = ['molecules.csv'] # pass in a list of CSV files
# csv_to_sqlite.write_csv(input_files, "../db.sqlite3.chem_molecule", options)