from itertools import cycle
from zipfile import ZipFile
from django.shortcuts import redirect, render

from django.http import Http404, JsonResponse, HttpResponse, FileResponse
from django.urls import reverse
from django.conf import settings
from django.utils.datastructures import MultiValueDictKeyError

import re
import os
import numpy as np
import pandas as pd
import bokeh.plotting as bp
from bokeh.plotting import curdoc
from bokeh.embed import components
from bokeh.models import ColumnDataSource, Range1d, LogScale, LinearScale, LinearAxis, Select, FixedTicker, BasicTickFormatter
from bokeh.models.callbacks import CustomJS
from bokeh.models import CustomJSTickFormatter
from bokeh.layouts import column, row
from bokeh.palettes import Spectral7
# from bokeh.palettes import Bright


from chem.models import Molecule, Isotopologue
from linelist.models import HRMeta
from news.models import SiteUpdate
from .utils import make_decimal_timestamp, make_zip_bundle


def home(request):
    df = pd.read_csv(settings.RES_DIR / 'ExoMolHR_list.csv')
    recent_updates = SiteUpdate.objects.all().order_by('-date', '-id')[:10]
    context = {
        'total_lines': f"{int(df['HR N lines'].sum()):,}",
        'num_iso': df['iso-slug'].count(),
        'num_mol': len(df['molecule'].drop_duplicates()),
        'recent_updates': recent_updates
    }
    return render(request, "linelist/home.html", context)


def qnlabel(request):
    import csv

    def split_csv_field(value):
        if not value:
            return []
        return [item.strip() for item in value.split(',') if item is not None and item.strip() != '']

    def clean_formula_text(value):
        if not value:
            return ''
        return value.replace('_p', '<sup>+</sup>').replace('-', '')

    def molecule_to_html(formula):
        txt = clean_formula_text((formula or '').strip())
        txt = re.sub(r'([A-Za-z\)])(\d+)', r'\1<sub>\2</sub>', txt)
        return txt

    def iso_slug_to_html(slug):
        raw = (slug or '').strip().replace('_p', '+')
        chunks = []
        for token in raw.split('-'):
            m = re.match(r'^(\d+)([A-Za-z]+)(\d*)$', token)
            if m:
                mass, elem, count = m.groups()
                part = f"<sup>{mass}</sup>{elem}"
                if count:
                    part += f"<sub>{count}</sub>"
                chunks.append(part)
            else:
                token = token.replace('+', '<sup>+</sup>')
                token = re.sub(r'([A-Za-z\)])(\d+)', r'\1<sub>\2</sub>', token)
                chunks.append(token)
        return ''.join(chunks)

    def clean_db_html(value):
        if not value:
            return ''
        return value.replace('_p', '<sup>+</sup>').replace('-', '')

    molecule_html_map = {
        m.ordinary_formula: clean_db_html(m.html) if m.html else molecule_to_html(m.ordinary_formula)
        for m in Molecule.objects.all().only('ordinary_formula', 'html')
    }

    isotopologue_html_map = {
        i.slug: clean_db_html(i.html) if i.html else iso_slug_to_html(i.slug)
        for i in Isotopologue.objects.all().only('slug', 'html')
    }

    # Read Iso QN Label Formats
    iso_list = []
    with open(settings.RES_DIR / 'ExoMolHR_list.csv', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            mol = row['molecule']
            iso = row['iso-slug']
            main_lbl = row['Main column']
            main_fmt = row['Main format']
            qn_lbl = row['QN label']
            qn_fmt = row['QN format']

            main_pairs = list(zip(split_csv_field(main_lbl), split_csv_field(main_fmt)))

            J_pair = []
            for lbl, fmt in main_pairs:
                if "J" in lbl:
                    J_pair.append((lbl, fmt))
                    break

            qn_pair = list(zip(split_csv_field(qn_lbl), split_csv_field(qn_fmt)))

            molecule_html = molecule_html_map.get(mol, molecule_to_html(mol))
            isotopologue_html = isotopologue_html_map.get(iso, iso_slug_to_html(iso))

            iso_list.append({
                'molecule': mol,
                'isotopologue': iso,
                'molecule_html': molecule_html,
                'isotopologue_html': isotopologue_html,
                'J_pair': J_pair,
                'qn_pair': qn_pair
            })

    # Read QN Label Format Descriptions
    desc_list = []
    with open(settings.RES_DIR / 'qn_label_fmt_desc.csv', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            label = row['Label']
            desc = row['Description']
            f_fmt = row['Fortran Format']
            c_fmt = row['C Format']

            desc_list.append({
                'label': label,
                'fortran': f_fmt,
                'c': c_fmt,
                'desc': desc.strip()
            })

    context = {
        'iso_list': iso_list,
        'desc_list': desc_list
    }
    return render(request, "linelist/qnlabel.html", context)


def about(request):
    df = pd.read_csv(settings.RES_DIR / 'ExoMolHR_list.csv')
    context = {
        'total_lines': f"{int(df['HR N lines'].sum()):,}",
        'num_iso': df['iso-slug'].count(),
        'num_mol': len(df['molecule'].drop_duplicates())
    }
    return render(request, "linelist/about.html", context)


def api(request):
    return render(request, "linelist/api.html")


def citation(request):
    return render(request, "linelist/citation.html")


def updates(request):
    all_updates = SiteUpdate.objects.all().order_by('-date', '-id')
    return render(request, "linelist/updates.html", {'all_updates': all_updates})


def exomolhr_all_json(request):
    master_path = settings.RES_DIR / "exomolhr.all.json"
    if not master_path.exists():
        raise Http404("exomolhr.all.json not found")
    return FileResponse(open(master_path, "rb"),content_type="application/json")


def get_linelist(request):
    if request.GET.get("molecule"):
        molecules = request.GET.getlist("molecule")
        return select_isotopologues(request, molecules)
    if request.GET.get("iso"):
        iso_slugs = request.GET.getlist("iso")
        return select_filters(request, iso_slugs)
    return select_molecules(request)


def select_molecules(request):
    molecules = Molecule.objects.all().order_by('ordinary_formula')
    c = {"molecules": molecules}
    return render(request, "linelist/molecules.html", c)


def select_isotopologues(request, selected_molecules):
    isos = Isotopologue.objects.filter(molecule__slug__in=selected_molecules).prefetch_related('hrmeta_set').order_by('molecule__ordinary_formula', 'ordinary_formula')
    
    # Load Tmax data from CSV
    try:
        df = pd.read_csv(settings.RES_DIR / 'ExoMolHR_list.csv')
        tmax_df = df[['iso-slug', 'Tmax']].dropna(subset=['Tmax'])
        tmax_dict = dict(zip(tmax_df['iso-slug'], tmax_df['Tmax'].astype(int)))
    except Exception:
        tmax_dict = {}

    for iso in isos:
        hrmeta = iso.hrmeta_set.first()
        if hrmeta:
            iso.pf_file = "__".join(f for f in hrmeta.data_filename.split("__")[1:]) + ".pf"
            iso.data_filename = hrmeta.data_filename
        else:
            iso.pf_file = f"{iso.slug}.pf"
            iso.data_filename = None
            
        # Bind the matched Tmax, default to N/A if missing
        iso.tmax = tmax_dict.get(iso.slug, 'N/A')
        
    c = {"isos": isos, "nisos": isos.count(), "DATA_URL": settings.DATA_URL}
    return render(request, "linelist/isotopologues.html", c)


def view_pf(request, pf_filename):
    pf_path = settings.DATA_DIR / 'pf' / pf_filename
    if not pf_path.exists():
        raise Http404("Partition function file not found.")
    try:
        with open(pf_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        raise Http404(f"Error reading file: {e}")
    return HttpResponse(content, content_type="text/plain; charset=utf-8")


def download_csv(request, csv_filename):
    import os
    from pathlib import Path
    import mimetypes
    
    # Ensure it only accesses the intended directory
    safe_filename = os.path.basename(csv_filename).strip()
    
    if not safe_filename.endswith(".csv"):
        return redirect("linelist:download_csv", csv_filename=f"{safe_filename}.csv", permanent=True)

    file_path = settings.DATA_DIR / 'csv' / safe_filename
    
    if file_path.exists():
        content_type, encoding = mimetypes.guess_type(str(file_path))
        if not content_type:
            content_type = 'text/plain'
            
        # USER REQUEST: .json and .pf should display inline (as_attachment=False)
        # .csv should be downloaded directly (as_attachment=True)
        is_inline = any(safe_filename.endswith(ext) for ext in ['.json', '.pf'])
        as_attachment = not is_inline
        
        return FileResponse(open(file_path, "rb"), content_type=content_type, as_attachment=as_attachment, filename=safe_filename)
    else:
        raise Http404(f"File '{safe_filename}' not found.")


def select_filters(request, iso_slugs):
    selected_isos = Isotopologue.objects.filter(slug__in=iso_slugs).order_by('molecule__ordinary_formula', 'ordinary_formula')

    # Load Tmax, vmin, vmax data from CSV
    try:
        df = pd.read_csv(settings.RES_DIR / 'ExoMolHR_list.csv')
        tmax_df = df[['iso-slug', 'Tmax']].dropna(subset=['Tmax'])
        tmax_dict = dict(zip(tmax_df['iso-slug'], tmax_df['Tmax'].astype(int)))
        vmin_dict = dict(zip(df['iso-slug'], df['vmin']))
        vmax_dict = dict(zip(df['iso-slug'], df['vmax']))
    except Exception:
        tmax_dict, vmin_dict, vmax_dict = {}, {}, {}

    tmax_values = []
    vmin_values = []
    vmax_values = []

    for iso in selected_isos:
        iso.tmax = tmax_dict.get(iso.slug, 'N/A')
        raw_vmin = vmin_dict.get(iso.slug, 0)
        raw_vmax = vmax_dict.get(iso.slug, 100000)
        iso.vmin = f"{float(raw_vmin):.4f}" if raw_vmin is not None else "0.0000"
        iso.vmax = f"{float(raw_vmax):.4f}" if raw_vmax is not None else "100000.0000"
        try:
            tmax_values.append(float(iso.tmax))
        except (ValueError, TypeError):
            pass
        try:
            vmin_values.append(float(raw_vmin))
        except (ValueError, TypeError):
            pass
        try:
            vmax_values.append(float(raw_vmax))
        except (ValueError, TypeError):
            pass

    min_tmax = int(min(tmax_values)) if tmax_values else 'N/A'
    global_vmin = round(min(vmin_values), 4) if vmin_values else 0
    global_vmax = round(max(vmax_values), 4) if vmax_values else 100000

    # Wavelength bounds (inverse of wavenumber)
    global_wvmin = round(1e7 / global_vmax, 4) if global_vmax > 0 else 0
    global_wvmax = round(1e7 / global_vmin, 4) if global_vmin > 0 else 100000

    c = {
        "selected_isos": selected_isos,
        "min_tmax": min_tmax,
        "global_vmin": global_vmin,
        "global_vmax": global_vmax,
        "global_wvmin": global_wvmin,
        "global_wvmax": global_wvmax,
    }
    return render(request, "linelist/dofilters.html", c)


def get_data(request):
    if not request.GET:
        raise Http404

    T = float(request.GET.get("T"))
    Smin = request.GET.get("Smin")
    if not Smin:
        Smin = 1e-30 
    Smin = float(Smin)
    iso_slugs = request.GET.getlist("iso")
    isos = Isotopologue.objects.filter(slug__in=iso_slugs)

    def get_default_numax(isos):
        return 100000
    def get_default_numin(isos):
        return 0.1


    try:
        numin = request.GET['numin']
        select_by_wavelength = False
    except MultiValueDictKeyError:
        select_by_wavelength = True

    if not select_by_wavelength:
        if isinstance(numin, str):
            numin = numin.replace('≥', '').replace('≤', '').strip()
            
        if numin == '':
            numin = 0
        else:
            numin = float(numin)
        try:
            numax_val = request.GET["numax"]
            if isinstance(numax_val, str):
                numax_val = numax_val.replace('≥', '').replace('≤', '').strip()
            numax = float(numax_val)
        except ValueError:
            numax = get_default_numax(isos)
    else:
        wvmin = request.GET.get('wvmin', '0')
        if isinstance(wvmin, str):
            wvmin = wvmin.replace('≥', '').replace('≤', '').strip()
        wvmin = float(wvmin)
        if wvmin == 0:
            numax = get_default_numax(isos)
            wvmin = 1.e7 / numax
        else:
            numax = 1.e7 / wvmin
        try:
            wvmax_val = request.GET["wvmax"]
            if isinstance(wvmax_val, str):
                wvmax_val = wvmax_val.replace('≥', '').replace('≤', '').strip()
            wvmax = float(wvmax_val)
            numin = 1.e7 / wvmax
        except ValueError:
            numin = get_default_numin(isos)
            wvmax = 1.e7 / numin
        
    archive_name, archive_size, output_files, nlines, Smax = calc_spec(
        numin, numax, T, Smin, isos
    )

    request.session["iso_slugs"] = iso_slugs
    request.session["output_files"] = output_files
    request.session["numax"] = numax

    bokeh_html = get_bokeh_html(iso_slugs, numin, numax, Smax, Smin, output_files, select_by_wavelength)

    c = {
        "bokeh_html": bokeh_html,
        "isos": isos,
        "nlines": f"{nlines:,}",
        "Smin": Smin,
        "T": int(T),
        "numin": numin,
        "numax": numax,
        "wvmin": wvmin if select_by_wavelength else None,
        "wvmax": wvmax if select_by_wavelength else None,
        "archive_name": archive_name,
        "archive_size": archive_size,
        "select_by_wavelength": select_by_wavelength,
    }
    return render(request, "linelist/viewspec.html", c)


def download_archive(request):
    try:
        archive_name = request.GET["archive_name"]
    except KeyError:
        raise Http404
    
    import os
    archive_name = os.path.basename(archive_name)
    file_path = settings.RESULTS_DIR / archive_name
    
    if file_path.exists():
        return FileResponse(open(file_path, "rb"), as_attachment=True, filename=archive_name)
    else:
        raise Http404("File not found in results directory.")


def ajax_data(request):
    numin = float(request.GET.get("numin", 0))
    numax = request.GET.get("numax")
    if numax is None:
        numax = request.session["numax"]
    numax = float(numax)

    output_files = request.session.get("output_files", {})
    iso_slugs = request.session.get("iso_slugs", [])
    
    data = {}
    colors = cycle(Spectral7)
    for iso_slug in iso_slugs:
        isocolor = next(colors)
        if iso_slug in output_files:
            file_path = settings.RESULTS_DIR / output_files[iso_slug]
            if file_path.exists():
                df = pd.read_csv(file_path)
                df = df[(df["nu"] >= numin) & (df["nu"] <= numax)]
                data[f"x__{iso_slug}"] = df["nu"].tolist()
                data[f"y__{iso_slug}"] = df["S"].tolist()
                data[f"color__{iso_slug}"] = [isocolor] * len(df)
            else:
                data[f"x__{iso_slug}"] = []
                data[f"y__{iso_slug}"] = []
                data[f"color__{iso_slug}"] = []

    response = JsonResponse(data)
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Methods"] = "GET"
    response["Access-Control-Max-Age"] = "1000"
    response["Access-Control-Allow-Headers"] = "Content-Type"
    return response


def get_bokeh_html(iso_slugs, numin, numax, Smax, Smin=1e-35, output_files=None, select_by_wavelength=False):
    curdoc().theme = 'caliber'

    # Pre-load data to determine true data bounds for zooming
    all_sources = []
    color_list = []
    colors_iter = cycle(Spectral7)
    
    true_nu_min = float('inf')
    true_nu_max = float('-inf')

    for iso_slug in iso_slugs:
        isocolor = next(colors_iter)
        color_list.append(isocolor)
        nu_data, wv_nm_data, wv_um_data, y_data = [], [], [], []

        if output_files and iso_slug in output_files:
            file_path = settings.RESULTS_DIR / output_files[iso_slug]
            if file_path.exists():
                df = pd.read_csv(file_path)
                df = df[(df["nu"] >= numin) & (df["nu"] <= numax)]
                
                if not df.empty:
                    true_nu_min = min(true_nu_min, df["nu"].min())
                    true_nu_max = max(true_nu_max, df["nu"].max())
                
                nu_data = df["nu"].tolist()
                y_data = df["S"].tolist()
                wv_nm_data = (1e7 / df["nu"]).tolist()
                wv_um_data = (1e4 / df["nu"]).tolist()

        if select_by_wavelength:
            x_data = wv_nm_data[:]
        else:
            x_data = nu_data[:]

        source = ColumnDataSource(data=dict(
            x=x_data, y=y_data,
            nu=nu_data, wv_nm=wv_nm_data, wv_um=wv_um_data
        ))
        all_sources.append(source)

    # Use true bounds if data exists, otherwise fallback to form bounds
    if true_nu_min != float('inf') and true_nu_max != float('-inf'):
        margin = (true_nu_max - true_nu_min) * 0.02
        if margin == 0:
            margin = true_nu_min * 0.02 if true_nu_min != 0 else 0.1
        numin = max(0, true_nu_min - margin)
        numax = true_nu_max + margin

    # Compute wavelength ranges based on (possibly updated) bounds
    wvmin_nm = 1e7 / numax if numax > 0 else 100
    wvmax_nm = 1e7 / numin if numin > 0 else 1e7
    wvmin_um = wvmin_nm / 1000
    wvmax_um = wvmax_nm / 1000

    # Determine default x unit based on filter page selection
    if select_by_wavelength:
        default_x_unit = "Wavelength (nm)"
        default_x_label = "Wavelength, nm"
        x_start, x_end = wvmin_nm, wvmax_nm
        top_label = "Wavenumber, cm⁻¹"
        top_factor = 1e7
    else:
        default_x_unit = "Wavenumber (cm⁻¹)"
        default_x_label = "Wavenumber, cm⁻¹"
        x_start, x_end = numin, numax
        top_label = "Wavelength, nm"
        top_factor = 1e7

    if Smax == 0:
        Smax = 1e-30
    if Smin <= 0:
        Smin = 1e-35

    # Shared x_range and mode source for top axis formatter
    shared_x_range = Range1d(x_start, x_end)
    mode_source = ColumnDataSource(data=dict(factor=[top_factor]))

    # X-axis formatter for large/small numbers (unicode superscripts)
    x_sci_formatter_code = """
        var val = factor ? (factor / tick) : tick;
        if (val === 0) return "0";
        if (Math.abs(val) >= 10000 || Math.abs(val) <= 0.001) {
            var mStr = val.toExponential(1);
            var parts = mStr.split('e');
            var mantissa = parts[0];
            var exp = parseInt(parts[1]).toString();
            var supMap = {'0':'⁰', '1':'¹', '2':'²', '3':'³', '4':'⁴', '5':'⁵', '6':'⁶', '7':'⁷', '8':'⁸', '9':'⁹', '-':'⁻', '+':''};
            var expSup = "";
            for (var i = 0; i < exp.length; i++) {
                expSup += supMap[exp[i]] || exp[i];
            }
            return mantissa + "×10" + expSup;
        }
        if (Math.abs(val) >= 100) return val.toFixed(1);
        if (Math.abs(val) >= 1) return val.toFixed(2);
        return val.toFixed(4);
    """

    # Top axis formatter (reciprocal conversion + sci notation)
    top_formatter_code = x_sci_formatter_code.replace(
        "var val = factor ? (factor / tick) : tick;",
        "if (tick <= 0) return '';\n        var factor = mode_src.data['factor'][0];\n        var val = factor / tick;"
    )

    # Bottom axis formatter (just sci notation)
    bottom_formatter_code = x_sci_formatter_code.replace(
        "var val = factor ? (factor / tick) : tick;",
        "var val = tick;"
    )

    # Linear y-axis formatter: use major_label_overrides for MathText rendering
    import math

    def make_lin_tick_overrides(smax):
        """Generate ~5 evenly-spaced tick positions with unicode superscript labels."""
        if smax <= 0:
            return {}, []
        step = smax / 5
        overrides = {}
        ticks = [0]
        overrides[0] = "0"
        
        # Unicode mapping for superscripts
        sup_map = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")
        
        for i in range(1, 6):
            val = step * i
            s = f"{val:.1e}"
            mantissa_str, exp_str = s.split("e")
            exp_val = int(exp_str)
            exp_sup = str(exp_val).translate(sup_map)
            
            # Plain string, no MathJax ($$), so Bokeh uses the default axis font
            label = f"{mantissa_str}×10{exp_sup}"
            overrides[val] = label
            ticks.append(val)
        return overrides, ticks

    # (Data loading logic was moved to the top of the function to compute true data limits)

    # Helper to build a figure with a given y_axis_type
    def make_fig(y_axis_type):
        f = bp.figure(
            sizing_mode="stretch_width",
            height=500,
            tools="pan,wheel_zoom,box_zoom,save,reset,hover",
            x_axis_label=default_x_label,
            y_axis_label="Intensity, cm / molecule",
            output_backend="canvas",
            y_axis_type=y_axis_type,
        )
        f.toolbar.logo = None
        f.x_range = shared_x_range
        if y_axis_type == "log":
            f.y_range = Range1d(Smin * 0.5, Smax * 2.0)
        else:
            f.y_range = Range1d(0, Smax * 1.05)
            overrides, tick_vals = make_lin_tick_overrides(Smax)
            f.yaxis[0].ticker = FixedTicker(ticks=tick_vals)
            f.yaxis[0].major_label_overrides = overrides

        # Create bottom formatter
        f.xaxis[0].formatter = CustomJSTickFormatter(code=bottom_formatter_code)

        # Font sizes
        f.xaxis.axis_label_text_font_size = "16pt"
        f.xaxis.axis_label_text_font_style = "bold"
        f.yaxis.axis_label_text_font_size = "16pt"
        f.yaxis.axis_label_text_font_style = "bold"
        f.xaxis.major_label_text_font_size = "16pt"
        f.yaxis.major_label_text_font_size = "16pt"

        # Top axis (reciprocal conversion)
        top_fmt = CustomJSTickFormatter(args=dict(mode_src=mode_source), code=top_formatter_code)
        top_ax = LinearAxis(
            axis_label=top_label,
            formatter=top_fmt,
            axis_label_text_font_size="16pt",
            axis_label_text_font_style="bold",
            major_label_text_font_size="14pt",
        )
        f.add_layout(top_ax, 'above')

        # Add data glyphs (shared sources)
        for idx, slug in enumerate(iso_slugs):
            f.circle(
                x="x", y="y", color=color_list[idx], size=5, alpha=0.6,
                source=all_sources[idx], legend_label=slug,
            )
        f.legend.click_policy = "hide"
        return f, top_ax

    fig_log, top_axis_log = make_fig("log")
    fig_lin, top_axis_lin = make_fig("linear")
    fig_lin.visible = False

    # --- Controls ---

    # Y-axis scale selector (toggles figure visibility)
    y_select = Select(
        title="Y Scale", value="Log",
        options=["Log", "Linear"], width=120
    )
    y_callback = CustomJS(args=dict(
        fig_log=fig_log, fig_lin=fig_lin
    ), code="""
        if (cb_obj.value === "Log") {
            fig_log.visible = true;
            fig_lin.visible = false;
        } else {
            fig_log.visible = false;
            fig_lin.visible = true;
        }
    """)
    y_select.js_on_change('value', y_callback)

    # X-axis unit selector (updates both figures)
    x_select = Select(
        title="X Unit", value=default_x_unit,
        options=["Wavenumber (cm⁻¹)", "Wavelength (nm)", "Wavelength (μm)"],
        width=200
    )
    x_callback = CustomJS(args=dict(
        sources=all_sources,
        fig_log=fig_log, fig_lin=fig_lin,
        top_log=top_axis_log, top_lin=top_axis_lin,
        mode_src=mode_source,
        shared_xr=shared_x_range,
        numin=numin, numax=numax,
        wvmin_nm=wvmin_nm, wvmax_nm=wvmax_nm,
        wvmin_um=wvmin_um, wvmax_um=wvmax_um
    ), code="""
        const unit = cb_obj.value;
        for (const source of sources) {
            const d = source.data;
            if (unit.startsWith("Wavenumber")) {
                d['x'] = d['nu'].slice();
            } else if (unit.includes("nm")) {
                d['x'] = d['wv_nm'].slice();
            } else {
                d['x'] = d['wv_um'].slice();
            }
            source.change.emit();
        }

        const figs = [fig_log, fig_lin];
        const tops = [top_log, top_lin];
        for (let i = 0; i < figs.length; i++) {
            if (unit.startsWith("Wavenumber")) {
                figs[i].below[0].axis_label = "Wavenumber, cm⁻¹";
                tops[i].axis_label = "Wavelength, nm";
            } else if (unit.includes("nm")) {
                figs[i].below[0].axis_label = "Wavelength, nm";
                tops[i].axis_label = "Wavenumber, cm⁻¹";
            } else {
                figs[i].below[0].axis_label = "Wavelength, μm";
                tops[i].axis_label = "Wavenumber, cm⁻¹";
            }
        }

        if (unit.startsWith("Wavenumber")) {
            shared_xr.start = numin;
            shared_xr.end = numax;
            mode_src.data['factor'] = [1e7];
        } else if (unit.includes("nm")) {
            shared_xr.start = wvmin_nm;
            shared_xr.end = wvmax_nm;
            mode_src.data['factor'] = [1e7];
        } else {
            shared_xr.start = wvmin_um;
            shared_xr.end = wvmax_um;
            mode_src.data['factor'] = [1e4];
        }
        mode_src.change.emit();
    """)
    x_select.js_on_change('value', x_callback)

    # Compose layout
    controls = row(x_select, y_select)
    layout = column(controls, fig_log, fig_lin, sizing_mode="stretch_width")

    bokeh_script, bokeh_div = components(layout)
    html = '<div class="bokeh-plot">' + bokeh_script + bokeh_div + "</div>"
    return html

def process_iso_worker(iso_slug, ll_name, Q, numin, numax, T, Smin, filestem, results_dir):
    
    c, h, kB = 29979245800.0, 6.62607015e-34, 1.380649e-23
    c2 = h * c / kB
    c2oT = c2 / T
    fac = 1 / (8 * np.pi * c)
    abundance = 1
    
    df = pd.read_csv(ll_name)
    df = df[(df["nu"] >= numin) & (df["nu"] <= numax)].copy()
    
    nu = df["nu"]
    if len(df) > 0:
        S_vals = (
            fac
            * df["g'"]
            * df["A"]
            * np.exp(-c2oT * df['E"'])
            * (1 - np.exp(-c2oT * nu))
            / nu**2
            / Q
            * abundance
        )
        if "S" in df.columns:
            df["S"] = S_vals
        else:
            df.insert(1, "S", S_vals)
        df = df[df["S"] >= Smin]
    else:
        if "S" in df.columns:
            df["S"] = []
        else:
            df.insert(1, "S", [])

    output_filename = f"{filestem}__{iso_slug}__{int(T)}K.csv"
    df.to_csv(os.path.join(results_dir, output_filename), index=False)
    
    iso_nlines = len(df)
    isoSmax = df["S"].max() if iso_nlines > 0 else 0
    if pd.isna(isoSmax):
        isoSmax = 0
    
    return iso_slug, output_filename, iso_nlines, isoSmax

def calc_spec(numin, numax, T, Smin, isos):
    import concurrent.futures
    filestem = make_decimal_timestamp()
    nlines = 0
    output_files = {}
    Smax = 0
    
    jobs = []
    for iso in isos:
        hrmeta = HRMeta.objects.get(isotopologue=iso)
        ll_name = settings.DATA_DIR / 'csv' / f"{hrmeta.data_filename}.csv"
        Q = hrmeta.get_Q(T)
        jobs.append((iso.slug, ll_name, Q, numin, numax, T, Smin, filestem, settings.RESULTS_DIR))

    with concurrent.futures.ProcessPoolExecutor() as executor:
        futures = [executor.submit(process_iso_worker, *job) for job in jobs]
        for future in concurrent.futures.as_completed(futures):
            iso_slug, output_filename, iso_nlines, isoSmax = future.result()
            output_files[iso_slug] = output_filename
            nlines += iso_nlines
            if float(isoSmax) > float(Smax):
                Smax = float(isoSmax)

    archive_name = f"{filestem}.zip"
    archive_size = make_zip_bundle(archive_name, output_files.values())

    return archive_name, archive_size, output_files, nlines, Smax
