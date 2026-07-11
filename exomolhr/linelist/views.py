from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from html import escape
from pathlib import Path
from threading import Lock
from zipfile import ZipFile
from django.shortcuts import redirect, render

from django.http import Http404, JsonResponse, HttpResponse, FileResponse
from django.urls import reverse
from django.conf import settings
from django.utils.datastructures import MultiValueDictKeyError

import logging
import re
import os
import numpy as np
import pandas as pd
import bokeh.plotting as bp
from bokeh.plotting import curdoc
from bokeh.embed import components
from bokeh.models import ColumnDataSource, Range1d, LogScale, LinearScale, LinearAxis, Select, FixedTicker, BasicTickFormatter, Div, SaveTool
from bokeh.models.callbacks import CustomJS
from bokeh.models import CustomJSTickFormatter
from bokeh.events import DocumentReady
from bokeh.layouts import column, row, Spacer
# from bokeh.palettes import Bright


from chem.models import Molecule, Isotopologue
from linelist.models import HRMeta
from news.models import SiteUpdate
from .utils import make_decimal_timestamp, make_zip_bundle


logger = logging.getLogger(__name__)
download_counter_lock = Lock()
FULL_SCATTER_POINT_LIMIT = 200000
FULL_SCATTER_FORCE_LIMIT = 500000
MAX_POINTS_PER_ISO = 50000
MAX_TOTAL_PLOT_POINTS = 500000
TOP_K_PER_BIN = 1
PLOT_COLOR_STOPS = [
    "#c5bddf",  # pale purple
    "#8ea7e2",  # blue
    "#6fb9e7",  # sky blue
    "#a3cdc6",  # teal
    "#8ccd85",  # green
    "#acde8d",  # yellow green
    "#ecee77",  # yellow 
    "#efbc63",  # orange
]
PLOT_PRIORITY_COLORS = [
    "#6fb9e7",  # sky blue
    "#acde8d",  # yellow green
    "#ecee77",  # yellow 
    "#8ccd85",  # green
    "#8ea7e2",  # blue
    "#efbc63",  # orange
    "#a3cdc6",  # teal
    "#c5bddf",  # pale purple
]



def hex_to_rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def interpolate_color(stops, position):
    position = min(1.0, max(0.0, position))
    scaled = position * (len(stops) - 1)
    left = int(scaled)
    right = min(left + 1, len(stops) - 1)
    fraction = scaled - left
    left_rgb = hex_to_rgb(stops[left])
    right_rgb = hex_to_rgb(stops[right])
    return rgb_to_hex(tuple(
        round(left_rgb[i] + (right_rgb[i] - left_rgb[i]) * fraction)
        for i in range(3)
    ))


def contrast_order(count):
    if count <= 2:
        return list(range(count))
    order = []
    queue = [(0, count - 1)]
    seen = set()
    while queue:
        left, right = queue.pop(0)
        for idx in (left, right):
            if idx not in seen:
                order.append(idx)
                seen.add(idx)
        mid = (left + right) // 2
        if left < mid < right and mid not in seen:
            order.append(mid)
            seen.add(mid)
        if mid - left > 1:
            queue.append((left, mid))
        if right - mid > 1:
            queue.append((mid, right))
    return order[:count]


def get_plot_colors(count):
    """Return colors that prioritize blue, green, and yellow for small sets."""
    if count <= 0:
        return []
    colors = PLOT_PRIORITY_COLORS[:count]
    if len(colors) == count:
        return colors

    sample_count = max(count * 3, len(PLOT_COLOR_STOPS) * 8)
    sampled = [
        interpolate_color(PLOT_COLOR_STOPS, i / (sample_count - 1))
        for i in range(sample_count)
    ]
    for idx in contrast_order(sample_count):
        color = sampled[idx]
        if color not in colors:
            colors.append(color)
        if len(colors) == count:
            break
    return colors


def clean_formula_html(value):
    if not value:
        return ""
    return str(value).replace("_p", "<sup>+</sup>").replace("-", "")


def iso_slug_to_formula_html(slug):
    raw = (slug or "").strip().replace("_p", "+")
    chunks = []
    for token in raw.split("-"):
        m = re.match(r"^(\d+)([A-Za-z]+)(\d*)$", token)
        if m:
            mass, elem, count = m.groups()
            part = f"<sup>{escape(mass)}</sup>{escape(elem)}"
            if count:
                part += f"<sub>{escape(count)}</sub>"
            chunks.append(part)
        else:
            token = escape(token).replace("+", "<sup>+</sup>")
            token = re.sub(r"([A-Za-z\)])(\d+)", r"\1<sub>\2</sub>", token)
            chunks.append(token)
    return "".join(chunks)


def get_isotopologue_formula_html_by_slug(iso_slugs):
    iso_html_by_slug = {
        iso.slug: clean_formula_html(iso.html) if iso.html else iso_slug_to_formula_html(iso.slug)
        for iso in Isotopologue.objects.filter(slug__in=iso_slugs).only("slug", "html")
    }
    return {
        slug: iso_html_by_slug.get(slug, iso_slug_to_formula_html(slug))
        for slug in iso_slugs
    }


def make_html_plot_legend(iso_slugs, iso_html_by_slug, color_list, kind):
    glyph_style = "width:24px;height:4px;border-radius:2px;" if kind == "stick" else "width:10px;height:10px;border-radius:50%;"
    items = []
    for idx, slug in enumerate(iso_slugs):
        label = iso_html_by_slug.get(slug, iso_slug_to_formula_html(slug))
        color = color_list[idx]
        items.append(
            (
                "<button type='button' data-legend-index='{idx}' "
                "style='display:inline-flex;align-items:center;gap:6px;margin:4px 8px;padding:2px 4px;"
                "border:0;background:transparent;color:#333;font:12pt Arial, sans-serif;cursor:pointer;"
                "white-space:nowrap;line-height:1.25;'>"
                "<span aria-hidden='true' style='display:inline-block;flex:0 0 auto;background:{color};{glyph_style}'></span>"
                "<span>{label}</span>"
                "</button>"
            ).format(idx=idx, color=color, glyph_style=glyph_style, label=label)
        )
    return (
        "<div class='exomolhr-plot-legend' "
        "style='display:flex;flex-wrap:wrap;justify-content:center;align-items:center;"
        "gap:2px 6px;margin:6px 8px 2px;padding:4px 8px;'>"
        + "".join(items)
        + "</div>"
    )


def format_plot_range_value(value):
    return f"{float(value):.6f}"


def get_isotope_slug_for_plot_filename(iso_slug):
    parts = str(iso_slug).split("__")
    if len(parts) >= 2:
        return parts[1]
    return str(iso_slug)


def make_plot_download_filename(filestem, iso_slugs, T, range_kind, range_min, range_max, unit, plot_kind):
    iso_part = "_".join(get_isotope_slug_for_plot_filename(iso) for iso in iso_slugs)
    range_part = (
        f"{range_kind}{format_plot_range_value(range_min)}-"
        f"{format_plot_range_value(range_max)}{unit}"
    )
    return f"{filestem}__{iso_part}__{int(T)}K__{range_part}__{plot_kind}.png"


def make_plot_download_filenames(filestem, iso_slugs, T, numin, numax, range_kind, range_min, range_max):
    if range_kind == "wl":
        wl_min_nm = float(range_min)
        wl_max_nm = float(range_max)
    else:
        wl_min_nm = 1e7 / float(numax) if float(numax) > 0 else 0
        wl_max_nm = 1e7 / float(numin) if float(numin) > 0 else 1e7

    return {
        "wn_stick": make_plot_download_filename(
            filestem, iso_slugs, T, "wn", numin, numax, "cm-1", "stick"
        ),
        "wn_scatter": make_plot_download_filename(
            filestem, iso_slugs, T, "wn", numin, numax, "cm-1", "scatter"
        ),
        "nm_stick": make_plot_download_filename(
            filestem, iso_slugs, T, "wl", wl_min_nm, wl_max_nm, "nm", "stick"
        ),
        "nm_scatter": make_plot_download_filename(
            filestem, iso_slugs, T, "wl", wl_min_nm, wl_max_nm, "nm", "scatter"
        ),
        "um_stick": make_plot_download_filename(
            filestem, iso_slugs, T, "wl", wl_min_nm / 1000, wl_max_nm / 1000, "um", "stick"
        ),
        "um_scatter": make_plot_download_filename(
            filestem, iso_slugs, T, "wl", wl_min_nm / 1000, wl_max_nm / 1000, "um", "scatter"
        ),
    }


def get_download_counter_path():
    configured_path = getattr(settings, "DOWNLOAD_COUNTER_FILE", None)
    if configured_path:
        return Path(configured_path)
    return Path(settings.RES_DIR) / "download_count.txt"


def update_download_count(increment=0):
    try:
        if increment is True:
            increment = 1
        elif increment is False:
            increment = 0
        else:
            increment = max(0, int(increment))

        counter_path = get_download_counter_path()
        with download_counter_lock:
            with open(counter_path, "r+", encoding="utf-8") as f:
                raw_count = f.read().strip()
                count = int(raw_count)

                if increment:
                    count += increment
                    f.seek(0)
                    f.truncate()
                    f.write(str(count))
                    f.flush()

                return count
    except Exception:
        logger.exception("Unable to update download counter at %s", get_download_counter_path())
        raise


def count_csv_files_in_archive(file_path):
    try:
        with ZipFile(file_path, "r") as archive:
            return sum(1 for name in archive.namelist() if name.lower().endswith(".csv"))
    except Exception:
        return 1


def floor_to_decimal(value, places=6):
    step = Decimal("1").scaleb(-places)
    return float(Decimal(str(value)).quantize(step, rounding=ROUND_FLOOR))


def ceil_to_decimal(value, places=6):
    step = Decimal("1").scaleb(-places)
    return float(Decimal(str(value)).quantize(step, rounding=ROUND_CEILING))


def home(request):
    df = pd.read_csv(settings.RES_DIR / 'ExoMolHR_list.csv')
    recent_updates = SiteUpdate.objects.all().order_by('-date', '-id')[:10]
    context = {
        'total_lines': f"{int(df['HR N lines'].sum()):,}",
        'num_iso': df['iso-slug'].count(),
        'num_mol': len(df['molecule'].drop_duplicates()),
        'download_count': f"{update_download_count():,}",
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
        'num_mol': len(df['molecule'].drop_duplicates()),
        'download_count': f"{update_download_count():,}",
    }
    return render(request, "linelist/about.html", context)


def download_count(request):
    return JsonResponse({"count": update_download_count()})


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
    update_download_count(increment=True)
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
    update_download_count(increment=True)
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
    
    if safe_filename.endswith(".parquet"):
        file_path = settings.DATA_DIR / 'cache' / safe_filename
    elif safe_filename.endswith(".csv"):
        file_path = settings.DATA_DIR / 'csv' / safe_filename
    else:
        return redirect("linelist:download_csv", csv_filename=f"{safe_filename}.csv", permanent=True)
    
    if file_path.exists():
        content_type, encoding = mimetypes.guess_type(str(file_path))
        if not content_type:
            content_type = 'application/octet-stream' if safe_filename.endswith(".parquet") else 'text/plain'
            
        # USER REQUEST: .json and .pf should display inline (as_attachment=False)
        # .csv should be downloaded directly (as_attachment=True)
        is_inline = any(safe_filename.endswith(ext) for ext in ['.json', '.pf'])
        as_attachment = not is_inline

        update_download_count(increment=True)
        
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
        iso.vmin = f"{float(raw_vmin):.6f}" if raw_vmin is not None else "0.000000"
        iso.vmax = f"{float(raw_vmax):.6f}" if raw_vmax is not None else "100000.000000"
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
    global_vmin = min(vmin_values) if vmin_values else 0
    global_vmax = max(vmax_values) if vmax_values else 100000

    # Wavelength bounds (inverse of wavenumber)
    global_wvmin = floor_to_decimal(1e7 / global_vmax, 6) if global_vmax > 0 else 0
    global_wvmax = ceil_to_decimal(1e7 / global_vmin, 6) if global_vmin > 0 else 100000

    c = {
        "selected_isos": selected_isos,
        "min_tmax": min_tmax,
        "global_vmin": f"{global_vmin:.6f}",
        "global_vmax": f"{global_vmax:.6f}",
        "global_wvmin": f"{global_wvmin:.6f}",
        "global_wvmax": f"{global_wvmax:.6f}",
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

    n_iso = len(iso_slugs)
    selected_range = max(0, numax - numin)
    MAX_ISOS_HARD = 30
    REQUEST_COST_LIMIT = 500000
    request_cost = n_iso * selected_range
    if n_iso > MAX_ISOS_HARD or request_cost > REQUEST_COST_LIMIT:
        return render(
            request,
            "linelist/request.html",
            {
                "n_iso": n_iso,
                "selected_range": f"{selected_range:.2f}",
                "request_cost": f"{request_cost:.0f}",
                "max_isos": MAX_ISOS_HARD,
                "cost_limit": REQUEST_COST_LIMIT,
                "numin": f"{numin:.6f}",
                "numax": f"{numax:.6f}",
            },
            status=400
        )

    # Count the request before reading/calculation starts, so cancelled clients
    # are still counted once the request is accepted as valid.
    accepted_download_count = max(1, len(iso_slugs))
    update_download_count(increment=accepted_download_count)

    if select_by_wavelength:
        result_range_kind = "wl"
        result_range_min = wvmin
        result_range_max = wvmax
    else:
        result_range_kind = "wn"
        result_range_min = numin
        result_range_max = numax

    archive_name, archive_size, output_files, nlines, Smax = calc_spec(
        numin,
        numax,
        T,
        Smin,
        isos,
        result_range_kind,
        result_range_min,
        result_range_max,
    )

    counted_archives = request.session.get("counted_archives", {})
    if not isinstance(counted_archives, dict):
        counted_archives = {}
    counted_archives[archive_name] = accepted_download_count
    request.session["counted_archives"] = counted_archives

    request.session["iso_slugs"] = iso_slugs
    request.session["output_files"] = output_files
    request.session["numax"] = numax

    bokeh_html = get_bokeh_html(
        iso_slugs,
        numin,
        numax,
        Smax,
        Smin,
        output_files,
        select_by_wavelength,
        T,
        Path(archive_name).stem,
        result_range_kind,
        result_range_min,
        result_range_max,
    )

    c = {
        "bokeh_html": bokeh_html,
        "isos": isos,
        "nlines": f"{nlines:,}",
        "Smin": Smin,
        "T": int(T),
        "numin": f"{numin:.6f}",
        "numax": f"{numax:.6f}",
        "wvmin": f"{wvmin:.6f}" if select_by_wavelength else None,
        "wvmax": f"{wvmax:.6f}" if select_by_wavelength else None,
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
        counted_archives = request.session.get("counted_archives", {})
        already_counted = isinstance(counted_archives, dict) and archive_name in counted_archives
        if already_counted:
            counted_archives.pop(archive_name, None)
            request.session["counted_archives"] = counted_archives
        else:
            update_download_count(increment=count_csv_files_in_archive(file_path))
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
    colors = get_plot_colors(len(iso_slugs))
    for idx, iso_slug in enumerate(iso_slugs):
        isocolor = colors[idx]
        if iso_slug in output_files:
            file_path = settings.RESULTS_DIR / output_files[iso_slug]
            if file_path.exists():
                df = read_result_plot_data(file_path, numin, numax)
                n_iso = max(1, len(iso_slugs))
                max_points_per_iso = min(
                    MAX_POINTS_PER_ISO,
                    max(20000, MAX_TOTAL_PLOT_POINTS // n_iso)
                )
                df = reduce_for_plot(
                    df,
                    x_col="nu",
                    y_col="S",
                    max_points=max_points_per_iso,
                    top_k=TOP_K_PER_BIN
                )

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


def reduce_for_plot(df, x_col="nu", y_col="S", max_points=50000, top_k=3):
    df = df[[x_col, y_col]].dropna()

    if len(df) <= max_points:
        return df.sort_values(x_col)

    n_bins = max(1, max_points // top_k)

    x_min = df[x_col].min()
    x_max = df[x_col].max()

    if x_min == x_max:
        return df.sort_values(x_col).head(max_points)

    bins = np.linspace(x_min, x_max, n_bins + 1)

    df = df.copy()
    df["_bin"] = np.digitize(df[x_col], bins)

    df_plot = (
        df.sort_values(y_col, ascending=False)
          .groupby("_bin", group_keys=False)
          .head(top_k)
          .sort_values(x_col)
    )

    return df_plot[[x_col, y_col]]


def get_result_parquet_path(csv_path):
    return Path(csv_path).with_suffix(".parquet")


def read_result_plot_data(csv_path, numin=None, numax=None):
    parquet_path = get_result_parquet_path(csv_path)
    filters = None
    if numin is not None and numax is not None:
        filters = [
            ("nu", ">=", float(numin)),
            ("nu", "<=", float(numax)),
        ]

    if parquet_path.exists():
        try:
            df = pd.read_parquet(parquet_path, columns=["nu", "S"], filters=filters)
        except Exception:
            logger.exception("Unable to read result Parquet cache %s; falling back to CSV %s", parquet_path, csv_path)
            df = pd.read_csv(csv_path, usecols=["nu", "S"])
    else:
        df = pd.read_csv(csv_path, usecols=["nu", "S"])

    if numin is not None and numax is not None:
        df = df[(df["nu"] >= numin) & (df["nu"] <= numax)]
    return df[["nu", "S"]].dropna().sort_values("nu")


def get_bokeh_html(
    iso_slugs,
    numin,
    numax,
    Smax,
    Smin=1e-35,
    output_files=None,
    select_by_wavelength=False,
    T=296,
    plot_filestem=None,
    range_kind="wn",
    range_min=None,
    range_max=None,
):
    curdoc().theme = 'caliber'
    request_numin = float(numin)
    request_numax = float(numax)
    if plot_filestem is None:
        plot_filestem = make_decimal_timestamp()
    if range_min is None:
        range_min = request_numin
    if range_max is None:
        range_max = request_numax
    plot_download_filenames = make_plot_download_filenames(
        plot_filestem,
        iso_slugs,
        T,
        request_numin,
        request_numax,
        range_kind,
        range_min,
        range_max,
    )
    default_plot_download_filename = (
        plot_download_filenames["nm_stick"] if select_by_wavelength else plot_download_filenames["wn_stick"]
    )

    # Pre-load data to determine true data bounds for zooming
    all_sources = []
    top_sources = []
    full_sources = []
    full_available_flags = []
    full_counts = []
    color_list = []
    iso_plot_stats = []
    plot_colors = get_plot_colors(len(iso_slugs))
    
    true_nu_min = float('inf')
    true_nu_max = float('-inf')

    for idx, iso_slug in enumerate(iso_slugs):
        isocolor = plot_colors[idx]
        color_list.append(isocolor)
        nu_data, wv_nm_data, wv_um_data, y_data = [], [], [], []

        if output_files and iso_slug in output_files:
            file_path = settings.RESULTS_DIR / output_files[iso_slug]
            if file_path.exists():
                df_full = read_result_plot_data(file_path, numin, numax)
                n_iso = max(1, len(iso_slugs))
                max_points_per_iso = min(
                    MAX_POINTS_PER_ISO,
                    max(20000, MAX_TOTAL_PLOT_POINTS // n_iso)
                )
                df = reduce_for_plot(
                    df_full,
                    x_col="nu",
                    y_col="S",
                    max_points=max_points_per_iso,
                    top_k=TOP_K_PER_BIN
                )
                
                if not df.empty:
                    true_nu_min = min(true_nu_min, df["nu"].min())
                    true_nu_max = max(true_nu_max, df["nu"].max())
                
                nu_data = df["nu"].tolist()
                y_data = df["S"].tolist()
                wv_nm_data = (1e7 / df["nu"]).tolist()
                wv_um_data = (1e4 / df["nu"]).tolist()
                if len(df_full) <= FULL_SCATTER_FORCE_LIMIT:
                    full_nu_data = df_full["nu"].tolist()
                    full_y_data = df_full["S"].tolist()
                    full_wv_nm_data = (1e7 / df_full["nu"]).tolist()
                    full_wv_um_data = (1e4 / df_full["nu"]).tolist()
                    full_available = True
                else:
                    full_nu_data, full_y_data, full_wv_nm_data, full_wv_um_data = [], [], [], []
                    full_available = False
                full_count = len(df_full)
                total_strength = float(df_full["S"].sum()) if full_count else 0.0
            else:
                full_nu_data, full_y_data, full_wv_nm_data, full_wv_um_data = [], [], [], []
                full_available = False
                full_count = 0
                total_strength = 0.0
        else:
            full_nu_data, full_y_data, full_wv_nm_data, full_wv_um_data = [], [], [], []
            full_available = False
            full_count = 0
            total_strength = 0.0

        initial_use_full = False
        current_nu_data = full_nu_data if initial_use_full else nu_data
        current_y_data = full_y_data if initial_use_full else y_data
        current_wv_nm_data = full_wv_nm_data if initial_use_full else wv_nm_data
        current_wv_um_data = full_wv_um_data if initial_use_full else wv_um_data

        if select_by_wavelength:
            x_data = current_wv_nm_data[:]
        else:
            x_data = current_nu_data[:]

        source = ColumnDataSource(data=dict(
            x=x_data, y=current_y_data,
            y0_log=[max(float(Smin), 1e-35) * 0.5] * len(current_y_data),
            y0_lin=[0] * len(current_y_data),
            nu=current_nu_data, wv_nm=current_wv_nm_data, wv_um=current_wv_um_data,
        ))
        all_sources.append(source)
        top_sources.append(ColumnDataSource(data=dict(
            nu=nu_data, y=y_data, wv_nm=wv_nm_data, wv_um=wv_um_data,
        )))
        full_sources.append(ColumnDataSource(data=dict(
            nu=full_nu_data, y=full_y_data, wv_nm=full_wv_nm_data, wv_um=full_wv_um_data,
        )))
        full_available_flags.append(full_available)
        full_counts.append(full_count)
        iso_plot_stats.append(dict(index=len(all_sources) - 1, full_count=full_count, total_strength=total_strength))

    plot_order = [
        item["index"]
        for item in sorted(
            iso_plot_stats,
            key=lambda item: (item["full_count"], item["total_strength"]),
            reverse=True,
        )
    ]

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
            tools="pan,wheel_zoom,box_zoom,reset,hover",
            x_axis_label=default_x_label,
            y_axis_label="Intensity, cm / molecule",
            output_backend="canvas",
            y_axis_type=y_axis_type,
        )
        save_tool = SaveTool(filename=default_plot_download_filename)
        f.add_tools(save_tool)
        f.toolbar.logo = None
        f.toolbar.active_inspect = None
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
        right_ax = LinearAxis(
            ticker=FixedTicker(ticks=[]),
            major_tick_line_color=None,
            minor_tick_line_color=None,
            major_label_text_color=None,
            axis_line_color="black",
        )
        f.add_layout(right_ax, 'right')

        # Add data glyphs in draw order. Stronger/denser spectra are drawn
        # first, so weaker/sparser spectra remain visible above them.
        segment_renderers = []
        circle_renderers = []
        segment_by_index = {}
        circle_by_index = {}
        y0_col = "y0_log" if y_axis_type == "log" else "y0_lin"
        for idx in plot_order:
            seg = f.segment(
                x0="x", y0=y0_col, x1="x", y1="y",
                color=color_list[idx], alpha=0.55, line_width=1,
                source=all_sources[idx],
            )
            cir = f.circle(
                x="x", y="y", color=color_list[idx], size=5, alpha=0.0,
                source=all_sources[idx],
            )
            segment_renderers.append(seg)
            circle_renderers.append(cir)
            segment_by_index[idx] = seg
            circle_by_index[idx] = cir
        segments_by_iso_index = [segment_by_index[idx] for idx in range(len(iso_slugs))]
        circles_by_iso_index = [circle_by_index[idx] for idx in range(len(iso_slugs))]
        return f, top_ax, segment_renderers, circle_renderers, segments_by_iso_index, circles_by_iso_index, save_tool

    fig_log, top_axis_log, segments_log, circles_log, segments_by_iso_log, circles_by_iso_log, save_tool_log = make_fig("log")
    fig_lin, top_axis_lin, segments_lin, circles_lin, segments_by_iso_lin, circles_by_iso_lin, save_tool_lin = make_fig("linear")
    fig_lin.visible = False

    iso_formula_html_by_slug = get_isotopologue_formula_html_by_slug(iso_slugs)
    top_legend_log = Div(
        text=make_html_plot_legend(iso_slugs, iso_formula_html_by_slug, color_list, "stick"),
        sizing_mode="stretch_width",
        disable_math=True,
    )
    full_legend_log = Div(
        text=make_html_plot_legend(iso_slugs, iso_formula_html_by_slug, color_list, "scatter"),
        sizing_mode="stretch_width",
        disable_math=True,
        visible=False,
    )
    top_legend_log.js_on_event(DocumentReady, CustomJS(args=dict(
        segments_log=segments_by_iso_log,
        segments_lin=segments_by_iso_lin,
        circles_log=circles_by_iso_log,
        circles_lin=circles_by_iso_lin,
    ), code="""
        window.exomolhrPlotLegendState = window.exomolhrPlotLegendState || Array(segments_log.length).fill(true);

        function collectRoots() {
            const roots = [document];
            const nodes = document.querySelectorAll('*');
            for (const node of nodes) {
                if (node.shadowRoot) {
                    roots.push(node.shadowRoot);
                }
            }
            return roots;
        }

        function setLegendButtonState(index, visible) {
            for (const root of collectRoots()) {
                const buttons = root.querySelectorAll(`[data-legend-index="${index}"]`);
                for (const button of buttons) {
                    button.style.opacity = visible ? "1" : "0.35";
                    button.style.textDecoration = visible ? "none" : "line-through";
                }
            }
        }

        function bindLegendButtons() {
            for (const root of collectRoots()) {
                const buttons = root.querySelectorAll("[data-legend-index]");
                for (const button of buttons) {
                    if (button.dataset.exomolhrLegendBound === "true") {
                        continue;
                    }
                    button.dataset.exomolhrLegendBound = "true";
                    button.addEventListener("click", function(event) {
                        event.preventDefault();
                        window.exomolhrPlotLegendToggle(Number(button.dataset.legendIndex));
                    });
                }
            }
        }

        window.exomolhrPlotLegendToggle = function(index) {
            const visible = !window.exomolhrPlotLegendState[index];
            window.exomolhrPlotLegendState[index] = visible;
            const renderers = [
                segments_log[index], segments_lin[index],
                circles_log[index], circles_lin[index],
            ];
            for (const renderer of renderers) {
                renderer.visible = visible;
            }
            setLegendButtonState(index, visible);
        };

        bindLegendButtons();
        for (let index = 0; index < segments_log.length; index++) {
            setLegendButtonState(index, window.exomolhrPlotLegendState[index]);
        }
    """))

    # --- Controls ---
    centered_select_stylesheet = """
        label {
            display: block;
            text-align: center;
            width: 100%;
            margin-bottom: 8px;
            font-size: 13px;
        }
        select {
            text-align: center;
            text-align-last: center;
            font-size: 13px;
        }
        option {
            text-align: center;
            font-size: 13px;
        }
    """

    # Y-axis scale selector (toggles figure visibility)
    y_select = Select(
        title="Y Scale", value="Log",
        options=["Log", "Linear"], width=100,
        stylesheets=[centered_select_stylesheet],
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
        width=180,
        stylesheets=[centered_select_stylesheet],
    )
    x_callback = CustomJS(args=dict(
        sources=all_sources,
        fig_log=fig_log, fig_lin=fig_lin,
        top_log=top_axis_log, top_lin=top_axis_lin,
        mode_src=mode_source,
        shared_xr=shared_x_range,
        numin=numin, numax=numax,
        wvmin_nm=wvmin_nm, wvmax_nm=wvmax_nm,
        wvmin_um=wvmin_um, wvmax_um=wvmax_um,
        save_tool_log=save_tool_log,
        save_tool_lin=save_tool_lin,
        filename_wn_stick=plot_download_filenames["wn_stick"],
        filename_wn_scatter=plot_download_filenames["wn_scatter"],
        filename_nm_stick=plot_download_filenames["nm_stick"],
        filename_nm_scatter=plot_download_filenames["nm_scatter"],
        filename_um_stick=plot_download_filenames["um_stick"],
        filename_um_scatter=plot_download_filenames["um_scatter"],
    ), code="""
        const unit = cb_obj.value;
        const isScatter = save_tool_log.filename.endsWith("__scatter.png");
        let saveFilename = isScatter ? filename_wn_scatter : filename_wn_stick;
        for (const source of sources) {
            const d = source.data;
            if (unit.startsWith("Wavenumber")) {
                d['x'] = d['nu'].slice();
            } else if (unit.includes("nm")) {
                d['x'] = d['wv_nm'].slice();
                saveFilename = isScatter ? filename_nm_scatter : filename_nm_stick;
            } else {
                d['x'] = d['wv_um'].slice();
                saveFilename = isScatter ? filename_um_scatter : filename_um_stick;
            }
            source.change.emit();
        }
        save_tool_log.filename = saveFilename;
        save_tool_lin.filename = saveFilename;

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

    full_warning = Div(
        text=(
            "<div style='padding:8px 10px;border-radius:6px;background:#fff3cd;"
            "color:#664d03;border:1px solid #ffecb5;font-size:13px;'>"
            f"Full scatter draws all available points up to {FULL_SCATTER_FORCE_LIMIT:,} points per iso. "
            f"Above {FULL_SCATTER_POINT_LIMIT:,} points per isotopologue it may render slowly; "
            f"above {FULL_SCATTER_FORCE_LIMIT:,}, that isotopologue is shown with Top-K instead. "
            "Zoom to a smaller range for true full scatter."
            "</div>"
        ),
        visible=False,
        sizing_mode="stretch_width",
    )

    plot_select = Select(
        title="Plot Mode", value="Top-K Stick Spectra",
        options=["Top-K Stick Spectra", "Full Scatter"], width=180,
        stylesheets=[centered_select_stylesheet],
    )
    focus_select = Select(
        title="Highlight Isotopologue", value="All",
        options=["All"] + list(iso_slugs), width=180,
        stylesheets=[centered_select_stylesheet],
    )

    renderer_slugs = [iso_slugs[idx] for idx in plot_order]
    renderer_indices = plot_order[:]
    mode_focus_callback = CustomJS(args=dict(
        sources=all_sources,
        top_sources=top_sources,
        full_sources=full_sources,
        full_available_flags=full_available_flags,
        full_counts=full_counts,
        fig_log=fig_log,
        fig_lin=fig_lin,
        x_select=x_select,
        plot_select=plot_select,
        focus_select=focus_select,
        full_warning=full_warning,
        segments_log=segments_log,
        segments_lin=segments_lin,
        circles_log=circles_log,
        circles_lin=circles_lin,
        top_legend_log=top_legend_log,
        full_legend_log=full_legend_log,
        save_tool_log=save_tool_log,
        save_tool_lin=save_tool_lin,
        renderer_slugs=renderer_slugs,
        renderer_indices=renderer_indices,
        full_limit=FULL_SCATTER_POINT_LIMIT,
        full_force_limit=FULL_SCATTER_FORCE_LIMIT,
        filename_wn_stick=plot_download_filenames["wn_stick"],
        filename_wn_scatter=plot_download_filenames["wn_scatter"],
        filename_nm_stick=plot_download_filenames["nm_stick"],
        filename_nm_scatter=plot_download_filenames["nm_scatter"],
        filename_um_stick=plot_download_filenames["um_stick"],
        filename_um_scatter=plot_download_filenames["um_scatter"],
        log_baseline=max(float(Smin), 1e-35) * 0.5,
    ), code="""
        const unit = x_select.value;
        const mode = plot_select.value;
        const isFullScatter = mode.startsWith("Full Scatter");
        const focus = focus_select.value;
        let blocked = false;

        for (let sourceIndex = 0; sourceIndex < sources.length; sourceIndex++) {
            const source = sources[sourceIndex];
            const d = source.data;
            const useFull = isFullScatter && full_available_flags[sourceIndex] === true;
            if (isFullScatter && full_counts[sourceIndex] > full_limit) {
                blocked = true;
            }

            const sourceData = useFull ? full_sources[sourceIndex].data : top_sources[sourceIndex].data;
            d['nu'] = sourceData['nu'].slice();
            d['y'] = sourceData['y'].slice();
            d['wv_nm'] = sourceData['wv_nm'].slice();
            d['wv_um'] = sourceData['wv_um'].slice();
            d['y0_log'] = Array(d['y'].length).fill(log_baseline);
            d['y0_lin'] = Array(d['y'].length).fill(0);

            if (unit.startsWith("Wavenumber")) {
                d['x'] = d['nu'].slice();
            } else if (unit.includes("nm")) {
                d['x'] = d['wv_nm'].slice();
            } else {
                d['x'] = d['wv_um'].slice();
            }
            source.change.emit();
        }

        full_warning.visible = blocked && isFullScatter;
        let saveFilename = isFullScatter ? filename_wn_scatter : filename_wn_stick;
        if (unit.includes("nm")) {
            saveFilename = isFullScatter ? filename_nm_scatter : filename_nm_stick;
        } else if (unit.includes("μm")) {
            saveFilename = isFullScatter ? filename_um_scatter : filename_um_stick;
        }
        save_tool_log.filename = saveFilename;
        save_tool_lin.filename = saveFilename;

        top_legend_log.visible = mode === "Top-K Stick Spectra";
        full_legend_log.visible = isFullScatter;

        const allSegments = segments_log.concat(segments_lin);
        const allCircles = circles_log.concat(circles_lin);
        for (let i = 0; i < allSegments.length; i++) {
            const orderIndex = i % renderer_slugs.length;
            const slug = renderer_slugs[orderIndex];
            const sourceIndex = renderer_indices[orderIndex];
            const fallbackTop = isFullScatter && full_available_flags[sourceIndex] !== true;
            const isFocused = focus === "All" || focus === slug;
            allSegments[i].glyph.line_alpha = (mode === "Top-K Stick Spectra" || fallbackTop) ? (isFocused ? 0.55 : 0.02) : 0.0;
            allCircles[i].glyph.fill_alpha = (isFullScatter && !fallbackTop) ? (isFocused ? 0.55 : 0.02) : 0.0;
            allCircles[i].glyph.line_alpha = (isFullScatter && !fallbackTop) ? (isFocused ? 0.55 : 0.02) : 0.0;
            allSegments[i].glyph.change.emit();
            allCircles[i].glyph.change.emit();
        }

        function applyFocusLayer(fig, segments, circles) {
            const dataRenderers = segments.concat(circles);
            const kept = fig.renderers.filter((renderer) => !dataRenderers.includes(renderer));
            const order = renderer_slugs.map((_, index) => index);
            if (focus !== "All") {
                const focusIndex = renderer_slugs.indexOf(focus);
                if (focusIndex >= 0) {
                    const currentIndex = order.indexOf(focusIndex);
                    if (currentIndex >= 0) {
                        order.splice(currentIndex, 1);
                    }
                    order.push(focusIndex);
                }
            }
            for (const idx of order) {
                kept.push(segments[idx]);
                kept.push(circles[idx]);
            }
            fig.renderers = kept;
            fig.change.emit();
        }

        applyFocusLayer(fig_log, segments_log, circles_log);
        applyFocusLayer(fig_lin, segments_lin, circles_lin);
    """)
    plot_select.js_on_change('value', mode_focus_callback)
    focus_select.js_on_change('value', mode_focus_callback)

    # Compose layout
    left_controls = row(x_select, y_select, spacing=12)
    right_controls = row(plot_select, focus_select, spacing=12)
    controls = row(left_controls, Spacer(sizing_mode="stretch_width"), right_controls, sizing_mode="stretch_width")
    layout = column(controls, full_warning, fig_log, fig_lin, top_legend_log, full_legend_log, sizing_mode="stretch_width")

    bokeh_script, bokeh_div = components(layout)
    html = '<div class="bokeh-plot">' + bokeh_script + bokeh_div + "</div>"
    return html


def get_cached_parquet_path(csv_path):
    return settings.DATA_DIR / 'cache' / f"{Path(csv_path).stem}.parquet"


def read_linelist_for_calculation(csv_path, numin, numax):
    parquet_path = get_cached_parquet_path(csv_path)

    if parquet_path.exists():
        try:
            return pd.read_parquet(
                parquet_path,
                filters=[
                    ("nu", ">=", float(numin)),
                    ("nu", "<=", float(numax)),
                ],
            ).copy()
        except Exception:
            logger.exception(
                "Unable to read Parquet cache %s; falling back to CSV %s",
                parquet_path,
                csv_path,
            )

    df = pd.read_csv(csv_path)
    return df[(df["nu"] >= numin) & (df["nu"] <= numax)].copy()


def format_smin_for_filename(value):
    value = float(value)
    if value == 0:
        return "0"
    return f"{value:.6g}".replace("E", "e").replace("e+", "e")


def make_result_output_filename(filestem, iso_slug, T, range_kind, range_min, range_max, Smin, extension="csv"):
    range_prefix = "wl" if range_kind == "wl" else "wn"
    range_part = f"{range_prefix}{float(range_min):.6f}-{float(range_max):.6f}"
    smin_part = f"Smin{format_smin_for_filename(Smin)}"
    return f"{filestem}__{iso_slug}__{int(T)}K__{range_part}__{smin_part}.{extension}"


def process_iso_worker(
    iso_slug,
    ll_name,
    Q,
    Q_ref,
    numin,
    numax,
    T,
    T_ref,
    Smin,
    filestem,
    results_dir,
    range_kind,
    range_min,
    range_max,
    numexpr_threads=1,
):
    
    c, h, kB = 29979245800.0, 6.62607015e-34, 1.380649e-23
    c2 = h * c / kB

    try:
        import numexpr as ne
        ne.set_num_threads(int(numexpr_threads))
        use_numexpr = True
    except ImportError:
        ne = None
        use_numexpr = False
    
    df = read_linelist_for_calculation(ll_name, numin, numax)

    if len(df) > 0:
        nu = df["nu"].to_numpy(dtype=np.float64, copy=False)
        Epp = df['E"'].to_numpy(dtype=np.float64, copy=False)
        # Prefer temperature-rescaling from reference intensity S(T_ref).
        # This assumes df["S"] is the reference intensity, normally at 296 K.
        if "S" in df.columns:
            S_ref = df["S"].to_numpy(dtype=np.float64, copy=False)
            invT = 1 / T
            invTref = 1 / T_ref
            q_ratio = Q_ref / Q 
            if use_numexpr:
                S_vals = ne.evaluate(
                    "S_ref * q_ratio "
                    "* exp(-c2 * Epp * (invT - invTref)) "
                    "* (1 - exp(-c2 * nu * invT)) "
                    "/ (1 - exp(-c2 * nu * invTref))"
                )
            else:
                S_vals = (
                    S_ref * q_ratio
                    * np.exp(-c2 * Epp * (invT - invTref))
                    * (1 - np.exp(-c2 * nu * invT))
                    / (1 - np.exp(-c2 * nu * invTref))
                )
            df["S"] = S_vals
        else:
            # Fallback: if the CSV does not contain S(T_ref), compute from A.
            # This keeps the function robust for older/local files.
            gp = df["g'"].to_numpy(dtype=np.float64, copy=False)
            A = df["A"].to_numpy(dtype=np.float64, copy=False)
            fac = 1 / (8 * np.pi * c)
            abundance = 1
            const = fac / Q
            c2oT = c2 / T
            if use_numexpr:
                S_vals = ne.evaluate(
                    "const * gp * A "
                    "* exp(-c2oT * Epp) "
                    "* (1 - exp(-c2oT * nu)) "
                    "/ (nu * nu)"
                )
            else:
                S_vals = (
                    const * gp * A
                    * np.exp(-c2oT * Epp)
                    * (1.0 - np.exp(-c2oT * nu))
                    / (nu * nu)
                )
            df.insert(1, "S", S_vals)
        # Apply intensity cutoff after converting to target temperature.
        df = df[df["S"] >= Smin]
    else:
        if "S" in df.columns:
            df["S"] = []
        else:
            df.insert(1, "S", [])

    output_filename = make_result_output_filename(
        filestem,
        iso_slug,
        T,
        range_kind,
        range_min,
        range_max,
        Smin,
    )
    output_path = Path(results_dir) / output_filename
    df.to_csv(output_path, index=False)
    try:
        df[["nu", "S"]].to_parquet(get_result_parquet_path(output_path), index=False)
    except Exception:
        logger.exception("Unable to write result Parquet plot cache for %s", output_path)
    
    iso_nlines = len(df)
    isoSmax = df["S"].max() if iso_nlines > 0 else 0
    if pd.isna(isoSmax):
        isoSmax = 0
    
    return iso_slug, output_filename, iso_nlines, isoSmax

def calc_spec(numin, numax, T, Smin, isos, range_kind="wn", range_min=None, range_max=None):
    import concurrent.futures
    filestem = make_decimal_timestamp()
    nlines = 0
    output_files = {}
    Smax = 0
    T_ref = 296
    if range_min is None:
        range_min = numin
    if range_max is None:
        range_max = numax

    jobs = []
    for iso in isos:
        hrmeta = HRMeta.objects.get(isotopologue=iso)
        ll_name = settings.DATA_DIR / 'csv' / f"{hrmeta.data_filename}.csv"
        Q = hrmeta.get_Q(T)
        Q_ref = hrmeta.get_Q(T_ref)
        jobs.append((
            iso.slug,
            ll_name,
            Q,
            Q_ref,
            numin,
            numax,
            T,
            T_ref,
            Smin,
            filestem,
            settings.RESULTS_DIR,
            range_kind,
            range_min,
            range_max,
        ))

    if len(jobs) == 1:
        job = jobs[0] + (4,)
        iso_slug, output_filename, iso_nlines, isoSmax = process_iso_worker(*job)
        output_files[iso_slug] = output_filename
        nlines += iso_nlines
        Smax = max(float(Smax), float(isoSmax))
    else:
        max_workers = min(2, len(jobs))
        jobs = [job + (2,) for job in jobs]
        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_iso_worker, *job) for job in jobs]
            for future in concurrent.futures.as_completed(futures):
                iso_slug, output_filename, iso_nlines, isoSmax = future.result()
                output_files[iso_slug] = output_filename
                nlines += iso_nlines
                Smax = max(float(Smax), float(isoSmax))

    archive_name = f"{filestem}.zip"
    archive_size = make_zip_bundle(archive_name, output_files.values())

    return archive_name, archive_size, output_files, nlines, Smax
