import numpy as np
import matplotlib.pyplot as plt

filename = "/Users/christian/www/exomolhr_results/CO2__12C-16O2__UCL-4000__(12C)(16O)2_web.csv"
nu_e, I = np.genfromtxt(filename, usecols=(0,3), skip_header=0, delimiter=',', unpack=True)

hit_name = "./663b7e80.out"
nu_h, S = np.genfromtxt(hit_name, usecols=(0,1), delimiter=',', unpack=True)

#plt.stem(nu_e, I, linefmt='C0-')
#plt.stem(nu_h, S, linefmt='C1-')
#plt.ylim(0, 1e-20)
plt.plot(nu_e, I)
plt.plot(nu_h, S)
plt.yscale('log')
plt.show()
