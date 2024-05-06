import os
import sys
import json
import math
from conf import exomolhr_root
sys.path.append(exomolhr_root)
os.environ['DJANGO_SETTINGS_MODULE'] = 'exomolhr.settings'

from pyvalem.formula import Formula

# Prepare the Django models
import django
django.setup()

from chem.models import Molecule, Isotopologue
from linelist.models import Linelist

csv_name = sys.argv[1]

def parse_filename(filename):
    filestem = os.path.splitext(os.path.basename(filename))[0]
    return filestem.split('__')

def parse_to_float(s):
    try:
        return float(s)
    except ValueError:
        return None

def parse_V(V):
    elec_state = V[1:11]
    v = int(V[11:13])
    Omega = int(V[13:15])
    assert Omega == 0
    return f'{elec_state} v={v} Omega={Omega}'

def parse_Q(Q):
    J = float(Q[10:13])
    kpar = Q[13:15].strip()
    return f'J={J} kpar={kpar}'

def parse_csv_line(line):
    fields = line.split(',')
    nu, S, A, gamma_air, gamma_self, Epp, n_air, delta_air = [parse_to_float(e) for e in fields[2:10]]
    Vi, Vf, Qi, Qf, = fields[10:14]
    statep = f'{parse_V(Vi)} {parse_Q(Qi)}'
    statepp = f'{parse_V(Vf)} {parse_Q(Qf)}'

    unc = parse_to_float(fields[14])
    gp, gpp = int(fields[17]), int(fields[18])

    ndp = int(-math.log10(unc) + 2)
    nu = round(nu, ndp)
    unc = round(unc, ndp)

    prms = {'nu': nu, 'A': A}
    for prm_name in 'gamma_air', 'gamma_self', 'n_air', 'delta_air':
        val = locals()[prm_name]
        if val is not None:
            prms[prm_name] = val
    prms_json = json.dumps(prms)


    return nu, unc, S, A, Epp, gp, gpp, qnp, qnpp, prms_json

molecule_slug, iso_slug, dataset_name = parse_filename(csv_name)
print(molecule_slug, iso_slug, dataset_name)

isotopologue = Isotopologue.objects.get(slug=iso_slug)

with open(csv_name) as fi:
    fi.readline()
    for line in fi:
        nu, unc, S, A, Epp, gp, gpp, qnp, qnpp, prms_json = parse_csv_line(line)
        print(nu, unc, S, A, Epp, gp, gpp, qnp, qnpp, prms_json)
        trans = Linelist(isotopologue=isotopologue, nu=nu, S=S, A=A, Epp=Epp,
                         gp=gp, gpp=gpp, qnp=qnp, qnpp=qnpp, prms_json=prms_json, unc=unc)
        trans.save()

