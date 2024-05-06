import re
import os
import requests
import wikipedia
import pandas as pd
from pyvalem.formula import Formula


filenames = os.listdir('/home/jingxin/data/exomolhr/loc_result/')
molecules = []
molhtmls = []
moltags = []
molnames = []
molmasses = []
isoslugs = [] 
isoformulas = []
isohtmls = []
isotags = []
isomasses = []
datasets = []
for file in filenames:
    piece = file.replace('.csv','').replace('_p','+').replace('_m','-').split('__')
    
    # Molecule
    molecule = piece[0]
    molecules.append(molecule)
    molhtmls.append(Formula(molecule).html)
    moltags.append(molecule.lower())
    molmasses.append(format(Formula(molecule).mass, '.6f'))
    # Search molecule names from NIST website and Wikipedia.
    r_search = requests.get('https://webbook.nist.gov/cgi/cbook.cgi?Formula='
                            +molecule.replace('+','%2B')+'&NoIon=on&Units=SI')
    title = r_search.text.split('<title>')[1].split('</title>')[0]
    if title != 'Search Results':
        molname = title
    else:
        link_list = re.findall(r"(?<=href=\").+?(?=\")", r_search.text)
        urls = []
        for url in link_list:
            if url.split('ID=')[0] == '/cgi/cbook.cgi?':
                urls.append(url)
        r_cgi = requests.get('https://webbook.nist.gov'+urls[0])
        molname = r_cgi.text.split('<title>')[1].split('</title>')[0]
    if molname == molecule:
        molname = wikipedia.page(molecule, auto_suggest=False).title
    molnames.append(molname.capitalize())
    
    # Isotopologue
    isotopologue = piece[1]
    isoformula = piece[3]
    isoslugs.append(isotopologue)
    isoformulas.append(isoformula)
    isohtmls.append(Formula(isoformula).html)
    isotags.append(isotopologue.replace('-','').lower())
    isomasses.append(format(Formula(isoformula).mass, '.6f'))
    
    # Dataset
    datasets.append(piece[2])
    
pieces_df = pd.DataFrame({'filename':filenames, 
                          'molecule':molecules, 'molhtml':molhtmls, 'moltag':moltags, 'molhtml':molhtmls, 'molname':molnames, 'molmass':molmasses,
                          'isoslug':isoslugs, 'isoformula':isoformulas, 'isohtml':isohtmls, 'isotag':isotags, 'isomass':isomasses, 
                          'dataset':datasets}).sort_values(by=['moltag','isotag','dataset'])
pieces_df['id'] = pieces_df.reset_index().index+1
pieces_colnames = ['id', 'filename', 'molecule', 'molhtml', 'moltag', 'molname', 'molmass',
                   'isoslug', 'isoformula', 'isohtml', 'isotag', 'isohtml', 'isomass', 'dataset']
pieces_df = pieces_df[pieces_colnames]


molecules_df = pieces_df[['molecule', 'molhtml', 'moltag', 'molname', 'molmass']].drop_duplicates().sort_values(by=['moltag'])
molecules_df['molid'] = molecules_df.reset_index().index+1
molecules_colnames = ['molid', 'molecule', 'molhtml', 'moltag', 'molname', 'molmass']
molecules_df = molecules_df[molecules_colnames]
molecules_df.to_csv('~/ExoMolHR-web/res/molecules.csv', index=False, columns=molecules_colnames)


isotopologues_df = pieces_df.loc[:, ['molecule', 'molformula', 'molname', 'isoslug', 'isoformula', 'isotag', 'isomass']].drop_duplicates()
isotopologues_df['id'] = isotopologues_df.reset_index().index+1
isotopologues_colnames = ['id', 'molecule', 'molformula', 'molname', 'isoslug', 'isoformula', 'isotag', 'isomass']
isotopologues_df = isotopologues_df[isotopologues_colnames]
isotopologues_df.to_csv('~/ExoMolHR-web/res/isotopologues.csv', index=False, columns=isotopologues_colnames)
