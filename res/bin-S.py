import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

filestem = '/Users/christian/www/exomolhr_results/12C-16O2__27Al-16O_web'
filename = filestem + '.hr'
df = pd.read_csv(filename,
                 header=None,
                 sep=r'\s+',
                 usecols=(0, 3, 5),
                 names='nu S iso'.split())

numin = min(df['nu'])
numax = max(df['nu'])
N = len(df)

dnus = [0.1, 1, 10]

def bin_data(dnu):
    r = -np.log10(dnu)
    bin_numin =  round(numin, int(r))
    nubins = np.arange(bin_numin, numax+dnu, dnu)
    Nbins = nubins.shape[0]
    Sbinned = {iso: np.zeros(Nbins) for iso in df['iso'].unique()}
    bin_numax = dnu
    j = 0
    for i, row in df.iterrows():
        x = row['nu']
        S = row['S']
        iso = row['iso']
        if x >= bin_numax:
            j += 1
            if j == Nbins:
                break
            bin_numax = (j + 1) * dnu
        Sbinned[iso][j] += S

    for iso, S in Sbinned.items():
        np.savetxt(f'{iso}__{dnu}.hr.S', np.vstack((nubins, S)).T, fmt=["%12.6f", "%10.3e"])

for dnu in dnus:
    print(dnu)
    bin_data(dnu)

