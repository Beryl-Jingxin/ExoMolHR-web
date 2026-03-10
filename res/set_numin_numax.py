import os
import sys

import pandas as pd

from conf import www_exomolhr_path
webapp_path = os.path.join(www_exomolhr_path, 'exomolhr')
sys.path.append(webapp_path)
os.environ['DJANGO_SETTINGS_MODULE'] = 'exomolhr.settings'

# Prepare the Django models
import django
django.setup()

from django.conf import settings
from linelist.models import HRMeta
linelists = HRMeta.objects.all()
for linelist in linelists:
    print(linelist.data_filename)
    data_filepath = settings.DATA_DIR / (linelist.data_filename + '.csv')
    df = pd.read_csv(data_filepath)
    numin = df.loc(axis=1)['nu'].min()
    numax = df.loc(axis=1)['nu'].max()
    print(numin, numax)
    linelist.numin = numin
    linelist.numax = numax
    linelist.save()
