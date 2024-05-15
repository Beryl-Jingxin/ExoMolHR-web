from itertools import cycle
from django.shortcuts import render

from django.http import Http404, JsonResponse
from django.urls import reverse
from django.conf import settings

import numpy as np
import pandas as pd
import bokeh.plotting as bp
from bokeh.embed import components
from bokeh.models import AjaxDataSource
from bokeh.models.callbacks import CustomJS
from bokeh.palettes import Bright

from chem.models import Molecule, Isotopologue
from linelist.models import HRMeta

def get_linelist(request):
    if request.GET.get('molecule'):
        molecules = request.GET.getlist('molecule')
        return select_isotopologues(request, molecules)
    if request.GET.get('iso'):
        iso_slugs = request.GET.getlist('iso')
        return select_filters(request, iso_slugs)
    return select_molecules(request)


def select_molecules(request):
    molecules = Molecule.objects.all()
    c = {'molecules': molecules}
    return render(request, 'linelist/molecules.html', c)


def select_isotopologues(request, selected_molecules):
    isos = Isotopologue.objects.filter(molecule__slug__in=selected_molecules)
    c = {'isos': isos}
    return render(request, 'linelist/isotopologues.html', c)


def select_filters(request, iso_slugs):
    selected_isos = Isotopologue.objects.filter(slug__in=iso_slugs)
    c = {'selected_isos': selected_isos}
    return render(request, 'linelist/dofilters.html', c)

def get_data(request):
    if not request.GET:
        raise Http404

    numin = float(request.GET.get('numin', 0))
    numax = float(request.GET['numax'])
    T = float(request.GET.get('T'))
    Smin = request.GET.get('Smin')
    if not Smin:
        Smin = 0
    Smin = float(Smin)
    iso_slugs = request.GET.getlist('iso')
    isos = Isotopologue.objects.filter(slug__in=iso_slugs)
    result_name, plot_spec_data, nlines = calc_spec(numin, numax, T, Smin, isos)

    request.session['iso_slugs'] = iso_slugs 
    request.session['plot_spec_data'] = plot_spec_data

    #nu, S, color = get_plot_spec(request, numin, numax)
    bokeh_html = get_bokeh_html(iso_slugs)

    c = {'bokeh_html': bokeh_html, 'isos': isos, 'nlines': nlines, 'Smin': Smin}
    return render(request, 'linelist/viewspec.html', c)

def ajax_data(request):
    numin = float(request.GET.get('numin', 0))
    numax = float(request.GET.get('numax', 42000))
    nu, S, color, dnu = get_plot_spec(request, numin, numax)
    data = {}
    iso_slugs = request.session['iso_slugs']
    width = dnu / 2
    for iso_slug in iso_slugs:
        data[f"x__{iso_slug}"] = nu[iso_slug]
        data[f"top__{iso_slug}"] = S[iso_slug]
        data[f"color__{iso_slug}"] = color[iso_slug]
        data[f'width__{iso_slug}'] = [width] * len(nu[iso_slug])
    response = JsonResponse(data)
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Methods"] = "GET"
    response["Access-Control-Max-Age"] = "1000"
    response["Access-Control-Allow-Headers"] = "Content-Type"
    return response

def get_plot_spec(request, numin, numax):
    Dnu = numax - numin
    if Dnu > 10000:
        dnu = 10
    elif Dnu > 1000:
        dnu = 1
    else:
        dnu = 0.1
    sdnu = str(dnu)

    iso_slugs = request.session['iso_slugs']
    nu, S, color = {}, {}, {}
    colors = cycle(Bright[7])
    for iso_slug in iso_slugs:
        plot_spec_data = request.session['plot_spec_data'][iso_slug]
        bnumin = plot_spec_data[sdnu]['numin']
        isoS = plot_spec_data[sdnu]['S']
        isoN = len(isoS)
        i = int((numin - bnumin) / dnu)
        i = max(i, 0)
        j = int((numax - bnumin) / dnu)
        j = min(j, len(isoS)-1)
        S[iso_slug] =  isoS[i:j]
        nS = len(isoS[i:j])
        #nu = np.linspace(bnumin, bnumin + dnu*nS, nS)
        isonu = np.linspace(bnumin, bnumin + dnu*(isoN-1), isoN)
        nu[iso_slug] = list(isonu[i:j])

        isocolor = next(colors)
        color[iso_slug] = [isocolor] * nS

    return nu, S, color, dnu

def get_bokeh_html(iso_slugs):
    fig = bp.figure(
        #y_axis_type="log",
        frame_width=1000,
        frame_height=800,
        title="PLOT",
        tools="box_zoom,wheel_zoom,reset",
        x_axis_label="Wavenumber (cm-1)",
        y_axis_label="Mean line strength per bin (cm2.molec-1)",
    )
    fig.toolbar.logo = None

    source = AjaxDataSource(method="GET",
                            data_url=reverse("linelist:ajax_data"),
                            name="ajax_plot_data_source")
#    fig.line('x', 'y', source=source)
    for iso_slug in iso_slugs:
        r = fig.vbar(x=f'x__{iso_slug}', top=f'top__{iso_slug}', color=f"color__{iso_slug}", width=f'width__{iso_slug}', source=source, legend_label=iso_slug)

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

def calc_spec(numin, numax, T, Smin, isos):

    def calc_S(Q, df):
        # Speed of light (cm.s-1), Planck constant (J.s) and Boltzmann constant (J.K-1).
        c, h, kB = 29979245800., 6.62607015e-34, 1.380649e-23
        # Second radiation constant (cm K)
        c2 = h * c / kB
        c2oT = c2 / T
        fac = 1 / (8 * np.pi * c)
        nu = df['Frequency']
        return fac * df["g'"] * df['A'] * np.exp(-c2oT * df['E"']) * (
                1 - np.exp(-c2oT * nu)) /  nu**2 / Q * abundance

    # TODO
    abundance = 1

    plot_spec_data = {}
    nlines = 0
    for iso in isos:
        hrmeta = HRMeta.objects.get(isotopologue=iso)
        ll_name = settings.DATA_DIR / f"{hrmeta.data_filename}.csv"
        df = pd.read_csv(ll_name)
        df.drop(df[df['Frequency'] < numin].index, inplace=True)
        df.drop(df[df['Frequency'] > numax].index, inplace=True)
        Q = hrmeta.get_Q(T)
        df['S'] = calc_S(Q, df)
        df.drop(df[df['S'] < Smin].index, inplace=True)
        nlines += len(df)
        plot_spec_data[iso.slug] = bin_spec(df, numin, numax)

    # TODO
    output_filename = "test.csv"
    # TODO
    #df.to_csv(settings.RESULTS_DIR / output_filename, header=True, index=False)
    return output_filename, plot_spec_data, nlines

def bin_spec(df, numin, numax):
    dnus = [0.1, 1, 10]
    def get_bins(dnu):
        r = int(-np.log10(dnu))
        bin_numin = round(numin, r)
        return np.arange(bin_numin, numax+dnu, dnu) + dnu / 2

    bins = {dnu: get_bins(dnu) for dnu in dnus}
    cuts = pd.cut(df['Frequency'], bins[dnus[0]], right=False, labels=bins[dnus[0]][:-1])
    specs = {str(dnus[0]): df['S'].groupby(cuts).sum() / dnus[0]}

    cuts = pd.cut(specs[str(dnus[0])].index, bins[dnus[1]], right=False, labels=bins[dnus[1]][:-1])
    specs[str(dnus[1])] = specs[str(dnus[0])].groupby(cuts).sum().rename_axis('Frequency') / dnus[1]

    cuts = pd.cut(specs[str(dnus[1])].index, bins[dnus[2]], right=False, labels=bins[dnus[2]][:-1])
    specs[str(dnus[2])] = specs[str(dnus[1])].groupby(cuts).sum().rename_axis('Frequency') / dnus[2]

    for dnu in dnus:
        specs[str(dnu)] = {"numin": bins[dnu][0],
                           "S": specs[str(dnu)].values.tolist()}
    #    specs[dnu].to_csv(settings.RESULTS_DIR / f'spec{dnu}.csv', header=True)
    return specs

