from django.shortcuts import render

from django.http import Http404, JsonResponse
from django.urls import reverse
from django.conf import settings

import pandas as pd
import bokeh.plotting as bp
from bokeh.embed import components
from bokeh.models import AjaxDataSource
from bokeh.models.callbacks import CustomJS

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

    numin = request.GET.get('numin', 0)
    numax = request.GET['numax']
    T = float(request.GET.get('T'))
    iso_slugs = request.GET.getlist('iso')
    isos = Isotopologue.objects.filter(slug__in=iso_slugs)
    result_name, plot_spec_data = calc_spec(numin, numax, T, isos)

    nu, S = get_spec(numin, numax)
    bokeh_html = get_bokeh_html(nu, S)

    c = {'nu': nu, 'S': S, 'bokeh_html': bokeh_html}
    return render(request, 'calculate/viewspec.html', c)

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

def get_spec(numin, numax):
    Dnu = numax - numin
    if Dnu > 10000:
        dnu = 10
    elif Dnu > 1000:
        dnu = 1
    else:
        dnu = 0.1
    nu = plot_spec_data[dnu]['nu']
    S = plot_spec_data[dnu]['S'][(nu >= numin) & (nu < numax)]
    nu = plot_spec_data[dnu]['nu'][(nu >= numin) & (nu < numax)]
    return nu, S


def get_bokeh_html(nu, S):
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

    source = AjaxDataSource(method="GET",
                            data_url=reverse("calculate:ajax_data"),
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

def calc_spec(numin, numax, T, isos):

    def calc_S(Q):
        pass

    for iso in isos:
        hrmeta = HRMeta.objects.get(isotopologue=iso)
        ll_name = settings.DATA_DIR / f"{hrmeta.data_filename}.csv"
        df = pd.read_csv(ll_name)
        Q = hrmeta.get_Q(T)
        df['S'] = calc_S(Q)
        print(df)
