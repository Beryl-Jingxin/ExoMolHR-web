from django.shortcuts import render, redirect
from django.http import (Http404, StreamingHttpResponse, HttpResponse, FileResponse,
                         HttpResponseRedirect, JsonResponse)
from django.views.generic import View
from django.urls import reverse
from django.forms.models import model_to_dict

from django.conf import settings

from .models import Linelists
from .filters import TransFilters
# from chem.models import Molecule, Isotopologue
from pyvalem.formula import Formula
import os, csv, sqlite3
import numpy as np
import pandas as pd

import bokeh.plotting as bp
from bokeh.embed import components
from bokeh.models import AjaxDataSource
from bokeh.models.callbacks import CustomJS

pieces_df = pd.read_csv(settings.EXOMOLHR_CSV_FILE, header=0)


def get_calculate_params(request):
    if request.GET.get('molecule'):
        molecules = request.GET.getlist('molecule')
        return select_isotopologues(request, molecules)
    if request.GET.get('iso'):
        iso_slugs = request.GET.getlist('iso')
        return select_filters(request, iso_slugs)
    return select_molecules(request)


def select_molecules(request):
    molecules_colnames = ['molid', 'molecule', 'molhtml', 'moltag', 'molname', 'molmass']
    molecule_df = pd.read_csv(settings.MOLECULES_CSV_FILE, header=0, names=molecules_colnames)
    context = {
        'columns': molecule_df.columns, 
        'rows': molecule_df.to_dict('records')}   
    return render(request, 'calculate/molecules.html', context)


def select_isotopologues(request, selected_molecules):
    isotopologues_df = pieces_df[pieces_df['molecule'].isin(selected_molecules)]
    isotopologues_df = isotopologues_df[['molecule', 'molhtml', 'molname', 'isoslug', 'isoformula', 
                                         'isohtml', 'isotag', 'isomass', 'dataset']].drop_duplicates()
    isotopologues_df['id'] = isotopologues_df.reset_index().index+1
    moleculeshtml = ', '.join(list(isotopologues_df['molhtml'].unique()))
    context = {'columns': isotopologues_df.columns, 
               'rows': isotopologues_df.to_dict('records'), 
               'moleculeshtml': moleculeshtml
               } 
    return render(request, 'calculate/isotopologues.html', context)


def select_filters(request, iso_slugs):
    filters_df = pieces_df[pieces_df[['isoslug']].isin(iso_slugs).all(axis=1)]

    filters_df['id'] = filters_df.reset_index().index+1
    moleculeshtml = ', '.join(list(filters_df['molhtml'].unique()))
    isotopologueshtml = ', '.join(list(filters_df['isohtml'].unique())) 
    datasetshtml = ', '.join(list(filters_df['dataset'].unique())) 
    filenames = ', '.join(list(filters_df['filename'].unique()))
    context = {'columns': filters_df.columns,
               'rows': filters_df.to_dict('records'), 
               'moleculeshtml': moleculeshtml,
               'isotopologueshtml': isotopologueshtml,
               'datasetshtml': datasetshtml,
               'filenames': filenames,
               'iso_slugs': iso_slugs,
               }  
    return render(request, 'calculate/dofilters.html', context)



def read_data_for_res(dnu, m):
    filename = settings.EXOMOLHR_RESULTS_DIR / f"{m['iso_slug']}__{dnu}.hr.S"
    nu, S = np.genfromtxt(filename, unpack=True)
    return {'nu': nu, 'S': S}

def read_data(m, data):
    for dnu in [0.1, 1, 10]:
        data[dnu] = read_data_for_res(dnu, m)
    return data

# XXX TODO XXX
metadata = {'iso_slug': '12C-16O2'}
data = {}
read_data(metadata, data)

def get_spec(data, numin, numax):
    Dnu = numax - numin
    if Dnu > 10000:
        dnu = 10
    elif Dnu > 1000:
        dnu = 1
    else:
        dnu = 0.1
    nu = data[dnu]['nu']
    S = data[dnu]['S'][(nu >= numin) & (nu < numax)]
    nu = data[dnu]['nu'][(nu >= numin) & (nu < numax)]
    print(dnu, len(S))
    return nu, S

def ajax_data(request):
    numin = float(request.GET.get('numin', 0))
    numax = float(request.GET.get('numax', 42000))
    nu, S = get_spec(data, numin, numax)
    response = JsonResponse(dict(x=nu.tolist(), top=S.tolist()))
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Methods"] = "GET"
    response["Access-Control-Max-Age"] = "1000"
    response["Access-Control-Allow-Headers"] = "Content-Type"
    return response

def get_bokeh_html(m, nu, S):
    fig = bp.figure(
        #y_axis_type="log",
        frame_width=1000,
        frame_height=800,
        title="PLOT",
        tools="box_zoom,wheel_zoom,reset",
        x_axis_label="X AXIS",
        y_axis_label="Y AXIS",
    )
    fig.toolbar.logo = None

    source = AjaxDataSource(method="GET", data_url=reverse("calculate:ajax_data"),
                            name="ajax_plot_data_source")
#    fig.line('x', 'y', source=source)
    fig.vbar('x', 'top', source=source)

    callback = CustomJS(args=dict(xr=fig.x_range), code="""
        $.ajax({
            url: 'ajax-data',
            data: {
              'numin': xr.start,
              'numax': xr.end
            },
            success: function (data) {
              var ds = Bokeh.documents[0].get_model_by_name('ajax_plot_data_source');
              ds.data = data;
            }
          });
    """)
    fig.x_range.js_on_change('start', callback)

    bokeh_script, bokeh_div = components(fig)
    html = '<div class="bokeh-plot">' + bokeh_script + bokeh_div + "</div>"
    return html





def get_data(request):
    #print(request.GET)

    # Jingxin's magic happens...
    # ... and we create the line list files.

    # 12C-16O2__27Al-16O_web.hr
    # 12C-16O2__0.1.hr.S
    # 12C-16O2__1.hr.S
    # 12C-16O2__10.hr.S
    # 27Al-16O2__0.1.hr.S
    # 27Al-16O2__1.hr.S
    # 27Al-16O2__10.hr.S

    numin, numax = 0, 10005
    nu, S = get_spec(data, numin, numax)
    bokeh_html = get_bokeh_html(metadata, nu, S)

    c = {'nu': nu, 'S': S, 'bokeh_html': bokeh_html}

    return render(request, 'calculate/viewspec.html', c)
