# Import all what we need.
import time
import requests
import argparse
import numpy as np
import pandas as pd
import numexpr as ne
from io import StringIO

### TODO Remove me ###
import sys, os
webapp_path = '/Users/christian/www/ExoMolHR-web/exomolhr'
sys.path.append(webapp_path)
os.environ['DJANGO_SETTINGS_MODULE'] = 'exomolhr.settings'
# Prepare the Django models
import django
django.setup()
### TODO Remove me ###


from django.conf import settings

# Check the number of this computer's CPUs.
import multiprocessing
cup_num = multiprocessing.cpu_count()
print(f"CPU number: {cup_num}")
from pandarallel import pandarallel
pandarallel.initialize(nb_workers=4,progress_bar=False)    # Initialize.
#pandarallel.initialize(nb_workers=16,progress_bar=True)    # Initialize.

from scipy.constants import h, c, k as kB
c *= 100 
c2 = h * c / kB                   # Second radiation constant (cm K)
pi_c_8 = 1 / (8 * np.pi * c)      # 8 * pi * c (cm-1 s)

# Path and Parameters.
'''Could be changed !'''
#########################################################
unc_path = settings.DATA_DIR / 'uncertainty_list.csv'
database_path = settings.EXOMOL_DATA_DIR
loc_result_path = settings.LOCAL_CSV_DIR
web_result_path = settings.EXOMOLHR_RESULTS_DIR

T = 296
iso = '12C-16O2'
min_frequency = 600.00
max_frequency = 800.00
max_uncertainty = 0.01 * 100
min_intensity = 1E-30
#########################################################



# Report time.
class Timer:    
    def start(self):
        self.start_CPU = time.process_time()
        self.start_sys = time.time()
        return self

    def end(self, *args):
        self.end_CPU = time.process_time()
        self.end_sys = time.time()
        self.interval_CPU = self.end_CPU - self.start_CPU
        self.interval_sys = self.end_sys - self.start_sys
        print('{:25s} : {}'.format('Running time on CPU', self.interval_CPU), 's')
        print('{:25s} : {}'.format('Running time on system', self.interval_sys), 's')


# Part 1: Get Molecule, Isotopologue, Dataset and Abundance.
'''
Get the names of molecule name, isotopologue name and dataset name from the api__urls.txt 
which saved the URLs with molecule, isotopologue and dataset. 
Combine them with '/' for reading files from folders more convenient later.
'''
def mol_param(isotopologue):
    colnames=['id','molecule','isotopologue','isoformula','dataset','abundance','Main column', 'Main format', 'QN label','QN format']
    molparam_df = pd.read_csv(unc_path, usecols=[0,1,2,3,4,5,6,7,8,9], names=colnames, header=0)     
    molparam = molparam_df[molparam_df['isotopologue'].isin([isotopologue])]
    molecule = molparam['molecule'].values[0]
    isoformula = molparam['isoformula'].values[0]
    dataset = molparam['dataset'].values[0]
    abundance = molparam['abundance'].values[0]
    qns_label = molparam['QN label'].values[0]
    qns_format = molparam['QN format'].values[0]
    mol_iso_ds_path = molecule + '/' + isotopologue + '/' + dataset
    print('Isotopologue \t:', isotopologue) 
    print('Isotopologue formula \t\t:', isoformula) 
    print('Dataset \t\t:', dataset)  
    print('Abundance \t\t:', abundance) 
    print('Quantumn number labels \t\t:', qns_label)
    print('Quantumn number formats \t:', qns_format, '\n')    
    return (molparam_df, isoformula, abundance, qns_label, qns_format, mol_iso_ds_path)


# Part 2: Read Linelist Files.


def get_Q(pf_df):
    max_T = pf_df.count()[0]
    if T > max_T:
        print('The maximum temperature is', max_T, 'K.')
        raise ValueError('Sorry, please type a smaller T.')
    elif T < 1:
        raise('Sorry, please type a new T which is larger than or equal to 1')

    Q = pf_df['Q'][T-1]
    print('The partition function at T =', T, 'K is', Q, '\n')
    return(Q)

## 2.1 Read Partition Function File.
# Read partition function with online webpage.
def read_web_pf(T, mol_iso_ds_path, isotopologue, dataset):
    '''Get partition function from ExoMol website directly.'''    
    pf_url = ('https://exomol.com/db/' + str(mol_iso_ds_path) + '/' + isotopologue + '__' + dataset + '.pf')
    pf_content = requests.get(pf_url).text
    print(pf_url)
    pf_col_name = ['T', 'Q']
    print('Read the partition function file.')
    pf_df = pd.read_csv(StringIO(pf_content), sep=r'\s+', names=pf_col_name, header=None)
    return get_Q(pf_df)

# Read partition function with local partition function file.
def read_exomol_pf(T, database_path, isotopologue, dataset):
    pf_filename = (database_path + mol_iso_ds_path + '/' + isotopologue + '__' + dataset + '.pf')
    pf_col_name = ['T', 'Q']
    print('Read the partition function file.')
    pf_df = pd.read_csv(pf_filename, sep='\\s+', names=pf_col_name, header=None)
    return get_Q(pf_df)


## 2.2 Calculating.

# Calculate intensity at the chosen temperature.
def cal_intensity(T, A, Epp, gp, Q, nu, abundance):
    c2_T = c2 / T
    I = ne.evaluate('gp * A * exp(-c2_T * Epp) * (1 - exp(-c2_T * nu)) * pi_c_8 / (nu ** 2) / Q * abundance')
    return I


## 2.3 Format the results.

### 2.3.1 Format the Quantumn Numbers.
def format_qns(loc_df, qns_label, qns_format):
    qn_label_list = qns_label.split(',')
    qn_format_list = qns_format.split(',')
    label_num = len(qn_label_list)
    qn_format = [format.replace(format[1:-1],str(pd.to_numeric(format[1:-1])+1)).replace("%",'{: >')+'}' for format in qn_format_list]
    print('***', loc_df)
    qn_label_u_list = [loc_df[qn_label_list[i]+"'"].map(qn_format[i].format) for i in range(label_num)]
    qn_label_l_list = [loc_df[qn_label_list[i]+'"'].map(qn_format[i].format) for i in range(label_num)]

    max_qn_format_num = 50
    max_qn_format = '{: <' + str(max_qn_format_num)+'s}'
    qn_label_u = pd.DataFrame(qn_label_u_list).sum(axis=0).parallel_map(max_qn_format.format)
    qn_label_l = pd.DataFrame(qn_label_l_list).sum(axis=0).parallel_map(max_qn_format.format)
    return(qn_label_u, qn_label_l)


### 2.3.2 Format All Results.
def format_results(loc_df, qns_label, qns_format, molecule, isotopologue, isoformula, dataset, abundance):

    A = pd.to_numeric(loc_df['A']).values
    Epp = pd.to_numeric(loc_df['E"']).values
    gp = pd.to_numeric(loc_df["g'"]).values
    nu = pd.to_numeric(loc_df['Frequency']).values
    #Q = read_exomol_pf(T, database_path, isotopologue, dataset)
    Q = read_web_pf(T, mol_iso_ds_path, isotopologue, dataset)
    I = cal_intensity(T, A, Epp, gp, Q, nu, abundance)
    
    qn_label_u, qn_label_l = format_qns(loc_df, qns_label, qns_format)
    web_df = pd.DataFrame()
    web_df['Frequency'] = pd.Series(nu).parallel_map('{: >12.6f}'.format)
    web_df['Uncertainty'] = pd.Series(loc_df['Uncertainty'].values).parallel_map('{: >12.6f}'.format)
    web_df['A'] = pd.Series(loc_df['A'].values).parallel_map('{: >10.4E}'.format)
    web_df['I'] = pd.Series(I)
    web_df['mol'] = molecule
    web_df['iso'] = isoformula
    web_df['ds'] = dataset
    web_df['E"'] = pd.Series(Epp).parallel_map('{: >12.6f}'.format)
    web_df["g'"] = pd.Series(loc_df["g'"].values).parallel_map('{: >6d}'.format)
    web_df['g"'] = pd.Series(loc_df['g"'].values).parallel_map('{: >6d}'.format)
    web_df["J'"] = pd.Series(loc_df["J'"].values).parallel_map('{: >7.1f}'.format)
    web_df['J"'] = pd.Series(loc_df['J"'].values).parallel_map('{: >7.1f}'.format)
    web_df["qn'"] = qn_label_u
    web_df['qn"'] = qn_label_l
    web_df = web_df[web_df['I'] > min_intensity]
    print('^^^^', web_df)
    order = ['Frequency', 'Uncertainty', 'A', 'I', 'mol', 'iso', 'ds', 'E"', "g'", 'g"', "J'", 'J"', "qn'", 'qn"']
    if web_df.empty:
        return web_df[order]
    web_df['I'] = web_df['I'].parallel_map('{: >10.4E}'.format)
    web_df = web_df[order]

    return(web_df)


# Part 3: Get Results.

# Read local results files and process the data to get the ExoMolHR web format result.
def read_loc_get_result(loc_result_path, mol_iso_ds_path, isoformula, qns_label, qns_format):
    
    # TODO refactor!
    molecule = mol_iso_ds_path.split('/')[0]
    dataset = mol_iso_ds_path.split('/')[2]
    print(loc_result_path)
    print(mol_iso_ds_path)
    print(isoformula)
    print(type(loc_result_path))
    web_df = pd.DataFrame()
    loc_result_filepath = loc_result_path / (mol_iso_ds_path.replace('/','__') + '__' + isoformula + '.csv')
    print('Read the local result file.')
    print(loc_result_filepath)
    print(type(loc_result_filepath))
    print(str(loc_result_filepath))
    read_loc = pd.read_csv(loc_result_filepath, header=0, chunksize=100_000_000,
                           iterator=True, low_memory=False)
    for chunk in read_loc:
        chunk = chunk[pd.to_numeric(chunk['Frequency']).between(min_frequency, max_frequency)]
        chunk = chunk[pd.to_numeric(chunk['Uncertainty']) < max_uncertainty]
        if chunk.empty:
            continue
        web_format_chunk = format_results(chunk, qns_label, qns_format, molecule, iso, isoformula, dataset, abundance)
        web_df = pd.concat([web_df, web_format_chunk])
    
    pd.set_option("display.max_columns",30)                           
    return(web_df)


t = Timer()
t.start()

molparam_df, isoformula, abundance, qns_label, qns_format, mol_iso_ds_path = mol_param(iso)
web_df = read_loc_get_result(loc_result_path, mol_iso_ds_path, isoformula, qns_label, qns_format)
web_df.to_csv(web_result_path / (mol_iso_ds_path.replace('/','__') + '__' + isoformula + '_web.csv'), header=True, index=False)
print('The web format result has been saved.')
    
t.end()

