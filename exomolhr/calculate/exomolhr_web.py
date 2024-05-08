# Import all what we need.
import time
import requests
import argparse
import numpy as np
import pandas as pd
import numexpr as ne
from io import StringIO


# Check the number of this computer's CPUs.
import multiprocessing
cup_num = multiprocessing.cpu_count()
print(f"CPU number: {cup_num}")
from pandarallel import pandarallel
pandarallel.initialize(nb_workers=4,progress_bar=False)    # Initialize.
#pandarallel.initialize(nb_workers=16,progress_bar=True)    # Initialize.


# Path and Parameters.
'''Could be changed !'''
#########################################################
def_path = '/home/jingxin/data/def/'
url_path = '/home/jingxin/data/url/'
unc_path = '/home/jingxin/ExoMolHR/uncertainty_list.csv'
database_path = '/mnt/data/exomol/exomol3_data/'
#database_path = '/home/jingxin/data/exomol_data/'
loc_result_path = '/home/jingxin/data/exomolhr/loc_result/'    # Create a folder for saving local format result files.
web_result_path = '/home/jingxin/data/exomolhr/web_result/'    # Create a folder for saving web format result files.

#T = 300
#molecule = 'AlH'
#min_frequency = 0.00
#max_frequency = 8000.00
#max_uncertainty = 0.001
#min_intensity = 10E-30
#########################################################


def parse_args():
    parse = argparse.ArgumentParser(description='ExoMolHR-web Program')
    parse.add_argument('-m', '--molecule', type=str, metavar='', required=True, help='Molecule name')
    parse.add_argument('-i', '--isotopologue', type=str, metavar='', required=True, help='Isotopologue name')
    parse.add_argument('-d', '--dataset', type=str, metavar='', required=True, help='Dataset name')
    parse.add_argument('-t', '--T', default=296, type=float, metavar='', help='Temperature')
    parse.add_argument('-u', '--max_uncertainty', default=0.001, type=float, metavar='', help='Maximum of uncertainty')
    parse.add_argument('-s', '--min_intensity', default=1E-30, type=float, metavar='', help='Minimum of intensity')
    parse.add_argument('-minv', '--min_frequency', default=0, type=float, metavar='', help='Minimum of frequency')
    parse.add_argument('-maxv', '--max_frequency', default=1E5, type=float, metavar='', help='Maximum of frequency')
    args = parse.parse_args()
    molecule = args.molecule
    isotopologue = args.isotopologue
    dataset = args.dataset
    T = args.T
    max_uncertainty = args.max_uncertainty
    min_intensity = args.min_intensity
    min_frequency = args.min_frequency
    max_frequency = args.max_frequency
    return molecule, isotopologue, dataset, T, max_uncertainty, min_intensity, min_frequency, max_frequency

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
def mol_param(unc_path, molecule, isotopologue, dataset, T):
    colnames=['id','molecule','isotopologue','isoformula','dataset','abundance','qn label','qn format']
    molparam_df = pd.read_csv(unc_path, usecols=[0,1,2,3,4,5,6,7], names=colnames, header=0)     
    molparam = molparam_df[molparam_df['molecule'].isin([molecule]) & 
                           molparam_df['isotopologue'].isin([isotopologue]) &
                           molparam_df['dataset'].isin([dataset])].values[0]
    isoformula = molparam[3]
    abundance = molparam[5]
    qns_label = molparam[6]
    qns_format = molparam[7]
    mol_iso_ds_path = molecule + '/' + isotopologue + '/' + dataset
    print('Molecule \t\t:', molecule)
    print('Isotopologue \t:', isotopologue) 
    print('Isotopologue formula \t\t:', isoformula) 
    print('Dataset \t\t:', dataset)  
    print('Abundance \t\t:', abundance) 
    print('Temperature \t:', T)  
    print('Quantumn number labels \t\t:', qns_label)
    print('Quantumn number formats \t:', qns_format, '\n')    
    return(molparam_df, isoformula, abundance, qns_label, qns_format, mol_iso_ds_path)


# Part 2: Read Linelist Files.

## 2.1 Read Partition Function File.
# Read partition function with online webpage.
def read_web_pf(T, mol_iso_ds_path, isotopologue, dataset):
    '''Get partition function from ExoMol website directly.'''    
    pf_url = ('https://exomol.com/db/' + mol_iso_ds_path + '/' + isotopologue + '__' + dataset + '.pf')
    pf_content = requests.get(pf_url).text
    pf_col_name = ['T', 'Q']
    print('Read the partition function file.')
    pf_df = pd.read_csv(StringIO(pf_content), sep='\\s+', names=pf_col_name, header=None)
    max_T = pf_df.count()[0]
    inNumberint = int(T)
    if T != inNumberint:
        raise Exception('Sorry, please type an integer as temperature.')
    elif T > max_T:
        print('The maximum temperature is', max_T, 'K.')
        raise Exception('Sorry, please type a smaller T.')
    elif T < 1:
        raise('Sorry, please type a new T which is larger than 0.')
    else:
        Q = pf_df['Q'][T-1]
        print('The partition function at T =', T, 'K is', Q, '\n')
    return(Q)

# Read partition function with local partition function file.
def read_exomol_pf(T, database_path, isotopologue, dataset):
    pf_filename = (database_path + mol_iso_ds_path + '/' + isotopologue + '__' + dataset + '.pf')
    pf_col_name = ['T', 'Q']
    print('Read the partition function file.')
    pf_df = pd.read_csv(pf_filename, sep='\\s+', names=pf_col_name, header=None)
    max_T = pf_df.count()[0]
    inNumberint = int(T)
    if T != inNumberint:
        raise Exception('Sorry, please type an integer as temperature.')
    elif T > max_T:
        print('The maximum temperature is', max_T, 'K.')
        raise Exception('Sorry, please type a smaller T.')
    elif T < 1:
        raise('Sorry, please type a new T which is larger than 0.')
    else:
        Q = pf_df['Q'][T-1]
        print('The partition function at T =', T, 'K is', Q, '\n')
    return(Q)


## 2.2 Calculating.

# Constants and Parameters.
molecule, isotopologue, dataset, T, max_uncertainty, min_intensity, min_frequency, max_frequency = parse_args()
import astropy.constants as ac
h = ac.h.to('J s').value          # Planck's const (J s)
c = ac.c.to('cm/s').value         # Velocity of light (cm s^{-1})
kB = ac.k_B.to('J/K').value       # Boltzmann's const (J K^{-1})
c2 = h * c / kB                   # Second radiation constant (cm K)
c2_T = - c2 / T                   # - c2 / T (cm)
pi_c_8 = 1 / (8 * np.pi * c)      # 8 * pi * c (cm-1 s)


# Calculate intensity at the chosen temperature.
def cal_intensity(A, Epp, gp, Q, v, c2_T, pi_c_8, abundance):
    I = ne.evaluate('gp * A * exp(c2_T * Epp) * (1 - exp(c2_T * v)) * pi_c_8 / (v ** 2) / Q * abundance')
    return(I)


## 2.3 Format the results.

### 2.3.1 Format the Quantumn Numbers.
def format_qns(loc_df, qns_label, qns_format):
    qn_label_list = qns_label.split(',')
    qn_format_list = qns_format.split(',')
    label_num = len(qn_label_list)
    qn_format = [format.replace(format[1:-1],str(pd.to_numeric(format[1:-1])+1)).replace("%",'{: >')+'}' for format in qn_format_list]
    qn_label_u_list = [loc_df[qn_label_list[i]+'_u'].map(qn_format[i].format) for i in range(label_num)]
    qn_label_l_list = [loc_df[qn_label_list[i]+'_l'].map(qn_format[i].format) for i in range(label_num)]

    max_qn_format_num = 50
    max_qn_format = '{: <' + str(max_qn_format_num)+'s}'
    qn_label_u = pd.DataFrame(qn_label_u_list).sum(axis=0).parallel_map(max_qn_format.format)
    qn_label_l = pd.DataFrame(qn_label_l_list).sum(axis=0).parallel_map(max_qn_format.format)
    return(qn_label_u, qn_label_l)


### 2.3.2 Format All Results.
def format(loc_df, qns_label, qns_format, molecule, isotopologue, isoformula, dataset, abundance):

    A = pd.to_numeric(loc_df['A']).values
    Epp = pd.to_numeric(loc_df['Epp']).values
    gp = pd.to_numeric(loc_df['gp']).values
    v = pd.to_numeric(loc_df['freq']).values
    Q = read_exomol_pf(T, database_path, isotopologue, dataset)
    I = cal_intensity(A, Epp, gp, Q, v, c2_T, pi_c_8, abundance)
    
    qn_label_u, qn_label_l = format_qns(loc_df, qns_label, qns_format)
    web_df = pd.DataFrame()
    web_df['freq'] = pd.Series(v).parallel_map('{: >12.6f}'.format)
    web_df['unc'] = pd.Series(loc_df['unc'].values).parallel_map('{: >12.6f}'.format)
    web_df['A'] = pd.Series(loc_df['A'].values).parallel_map('{: >10.4E}'.format)
    web_df['I'] = pd.Series(I)
    web_df['mol'] = molecule
    web_df['iso'] = isoformula
    web_df['ds'] = dataset
    web_df['Epp'] = pd.Series(Epp).parallel_map('{: >12.6f}'.format)
    web_df['gp'] = pd.Series(loc_df['gp'].values).parallel_map('{: >6d}'.format)
    web_df['gpp'] = pd.Series(loc_df['gpp'].values).parallel_map('{: >6d}'.format)
    web_df['Jp'] = pd.Series(loc_df['Jp'].values).parallel_map('{: >7.1f}'.format)
    web_df['Jpp'] = pd.Series(loc_df['Jpp'].values).parallel_map('{: >7.1f}'.format)
    web_df["qn'"] = qn_label_u
    web_df['qn"'] = qn_label_l
    web_df = web_df[web_df['I'] > min_intensity]
    web_df['I'] = web_df['I'].parallel_map('{: >10.4E}'.format)
    order = ['freq', 'unc', 'A', 'I', 'mol', 'iso', 'ds', 'Epp', 'gp', 'gpp', 'Jp', 'Jpp', "qn'", 'qn"']
    web_df = web_df[order]

    return(web_df)


# Part 3: Get Results.

# Read local results files and process the data to get the ExoMolHR web format result.
def read_loc_get_result(loc_result_path, mol_iso_ds_path, isoformula, qns_label, qns_format):
    
    web_df = pd.DataFrame()
    loc_result_filepath = loc_result_path + mol_iso_ds_path.replace('/','__') + '__' + isoformula + '.csv'
    print('Read the local result file.')
    read_loc = pd.read_csv(loc_result_filepath, header=0, chunksize=100_000_000,
                           iterator=True, low_memory=False)
    for chunk in read_loc:
        chunk = chunk[pd.to_numeric(chunk['freq']).between(min_frequency, max_frequency)]
        chunk = chunk[pd.to_numeric(chunk['unc']) < max_uncertainty]
        web_format_chunk = format(chunk, qns_label, qns_format, molecule, isotopologue, dataset, abundance)
    web_df = pd.concat([web_df, web_format_chunk])
    
    pd.set_option("display.max_columns",30)                           
    return(web_df)


t = Timer()
t.start()

molparam_df, isoformula, abundance, qns_label, qns_format, mol_iso_ds_path = mol_param(unc_path, molecule, isotopologue, dataset, T)
web_df = read_loc_get_result(loc_result_path, mol_iso_ds_path, isoformula, qns_label, qns_format)
web_df.to_csv(web_result_path + mol_iso_ds_path.replace('/','__') + '__' + isoformula + '_web.csv', header=True, index=False)
print('The web format result has been saved.')
    
t.end()

