# import datetime

from django.shortcuts import render
from django.http import Http404, StreamingHttpResponse, HttpResponse, FileResponse
from django.views.generic import View
from django.urls import reverse
from django.forms.models import model_to_dict

from .models import Linelist
from .filters import TransFilter
# from chem.models import Molecule, Isotopologue
from pyvalem.formula import Formula
import os, csv, sqlite3
import pandas as pd
from django.conf import settings


# Create your views here.

#con = sqlite3.connect('/home/jingxin/ExoMolHR-web/exomolhr/db.sqlite3', check_same_thread=False)
#db = con.cursor()
pieces_df = pd.read_csv(settings.EXOMOLHR_CSV_FILE, header=0)


def Home(request):
    return render(request, 'linelist/home.html')


def About(request):
    return render(request, 'linelist/about.html')


def Contact(request):
    return render(request, 'linelist/contact.html')


def molecule(request):
    molecules_colnames = ['molid', 'molecule', 'molhtml', 'moltag', 'molname', 'molmass']
    molecule_df = pd.read_csv(settings.MOLECULES_CSV_FILE, header=0, names=molecules_colnames)
    context = {'columns': molecule_df.columns, 'rows': molecule_df.to_dict('records')}    
    return render(request, 'linelist/molecule.html', context)
    
    
'''
def molecule(request):
    cursor = db.execute("SELECT id,formula,name,mass FROM 'chem_molecule'")
    colnames = ['id', 'formula', 'name', 'mass']
    idmolnm_df = pd.DataFrame(cursor.fetchall(), columns=colnames)
    idmolnm_df['mass'] = [Formula(formula).rmm for formula in idmolnm_df['formula'].values]
    idmolnm_df['formula'] = [Formula(formula).html for formula in idmolnm_df['formula'].values]
    context = {'columns': colnames, 'rows': idmolnm_df.to_dict('records')}   
    return render(request, 'linelist/molecule.html', context)
'''
    

def isotopologue(request, molecule):
    isotopologues_df = pieces_df[pieces_df['molecule'].isin([molecule])]
    isotopologues_df = isotopologues_df[['molecule', 'molhtml', 'molname', 
                                         'isoslug', 'isoformula', 'isohtml', 'isotag', 'isomass']].drop_duplicates()
    isotopologues_df['id'] = isotopologues_df.reset_index().index+1
    context = {'columns': isotopologues_df.columns, 
               'rows': isotopologues_df.to_dict('records'), 
               'molf': molecule, 
               'molh': Formula(molecule).html}   
    return render(request, 'linelist/isotopologue.html', context)

def dataset(request, molecule, isotopologue):
    datasets_df = pieces_df[pieces_df[['molecule', 'isoslug']].isin([molecule, isotopologue]).all(axis=1)]
    datasets_df = datasets_df[['molecule', 'molhtml', 'molname', 
                               'isoslug', 'isoformula', 'isohtml', 'isotag', 'isomass',
                               'dataset', 'filename']].drop_duplicates()
    datasets_df['id'] = datasets_df.reset_index().index+1    
    isoformula = list(datasets_df[datasets_df['isoslug'].isin([isotopologue])]['isoformula'])[0]
    context = {'columns': datasets_df.columns, 
               'rows': datasets_df.to_dict('records'), 
               'molf': molecule, 
               'molh': Formula(molecule).html, 
               'isos': isotopologue, 
               'isoh': Formula(isoformula).html}   
    return render(request, 'linelist/dataset.html', context)


def get_tip(header_name):
    if header_name == 'Frequency':
        header_tip = r"Wavenumber in cm<sup>-1</sup><br/><code>F12.6</code> | <code>12.6%</code>"
    else:
        header_tip = "You're on your own"
    return header_tip

def get_tip(header_names, localcsv_filename):
    header_labels = [col.replace("'","").replace('"','') for col in header_names]
    header_names_df = pd.DataFrame({'labelname':header_names, 'label':header_labels})
    EXOMOL_DIR = '/mnt/data/exomol/exomol3_data/'
    species_folder = '/'.join(localcsv_filename.split('__')[:3]) 
    def_json_filename = '__'.join(localcsv_filename.split('__')[1:3]) + '.json'
    def_json_path = EXOMOL_DIR + species_folder + '/' + def_json_filename
    def_json_df = pd.read_json(def_json_path, orient='columns')
    states_col_dict = def_json_df['dataset']['states']['states_file_fields']
    states_col_df = pd.DataFrame(states_col_dict)
    states_col_df['name'] = states_col_df['name'].str.replace('gtot','g')
    states_col_df['label'] = [col.split(':')[-1].replace('Sigma','Σ').replace('Lambda','Λ').replace('Omega','Ω') 
                            for col in states_col_df['name'].values]
    states_col_df['desc'] = '<br/>Description: ' + states_col_df['desc'].str.replace('-1','<sup>-1</sup>')
    states_col_df['fmt'] = ('Fortran format | C format<br/><code>' + states_col_df['ffmt'].str
                            .cat(states_col_df['cfmt'], sep='</code> | <code>') + '</code>')
    header_details_df = pd.merge(states_col_df, header_names_df, on='label')
    header_details_df['labelname'] = ('Label: ' + header_details_df['labelname'].str
                                    .replace("'", "' for upper state").str.replace('"','" for lower state'))
    main_tips = ['Label: Frenquency<br/>Description: Wavenumnber in cm<sup>-1</sup><br/>Fortran format | C format<br/><code>F12.6</code> | <code>%12.6f</code>',
    'Label: Uncertainty<br/>Description: Description: Energy uncertainty in cm<sup>-1</sup><br/>Fortran format | C format<br/><code>F12.6</code> | <code>%12.6f</code>',
    'Label: A<br/>Description: Einstein A coefficient<br/>Fortran format | C format<br/><code>ES10.4</code> | <code>%10.4E</code>']
    other_tips = (header_details_df['labelname'].astype(str) + '<br/>' + 
                  header_details_df['desc'].astype(str) + '<br/>' + 
                  header_details_df['fmt'].astype(str)).tolist()
    head_tips = main_tips + other_tips
    return(head_tips)


def species(request, molecule, isotopologue, dataset):
    source_link = f"https://www.exomol.com/data/molecules/{molecule}/{isotopologue}/{dataset}/"
    csvinf_df = pieces_df[pieces_df[['molecule', 'isoslug']].isin([molecule, isotopologue, dataset]).all(axis=1)]
    localcsv_filename = csvinf_df['filename'].values[0]
    localcsv_filepath = settings.LOCAL_CSV_DIR / f"loc_result/{localcsv_filename}"
    # Read the CSV file into a pandas DataFrame
    csv_df = pd.read_csv(localcsv_filepath, dtype=str).head(200)    
    header_names = [col.replace('Sigma','Σ').replace('Lambda','Λ').replace('Omega','Ω') for col in csv_df.columns]
    header_tips = get_tip(header_names, localcsv_filename)
    out = csv_df.to_dict('records')
    molhtml = csvinf_df['molhtml'].values[0]
    isohtml = csvinf_df['isohtml'].values[0]
    context = {'data': out, 
               'headers': zip(header_names, header_tips),
               'molf': molecule, 
               'molh': molhtml, 
               'isos': isotopologue, 
               'isoh': isohtml,
               'ds': dataset,
               'source_link': source_link}  
    return render(request, 'linelist/species.html', context)


def download_localfile(request, molecule, isotopologue, dataset):
    # Define the path to the file you want to download
    csvinf_df = pieces_df[pieces_df[['molecule', 'isoslug']].isin([molecule, isotopologue, dataset]).all(axis=1)]
    if not csvinf_df.empty:
        localcsv_filename = csvinf_df.iloc[0]['filename']
        localcsv_filepath = settings.DATA_DIR / f"loc_result/{localcsv_filename}"
        if os.path.exists(localcsv_filepath):
            with open(localcsv_filepath, 'rb') as file:
                # Set the content type of the response
                response = HttpResponse(file.read(), content_type='application/csv')
                # Set the legth for the downloaded file
                response['Content-Length'] = os.path.getsize(localcsv_filepath)
                # Set the filename for the downloaded file
                response['Content-Disposition'] = 'attachment; filename="%s"' % localcsv_filename
                return response
        else:
            raise Http404("File not found")
    else:
        raise Http404("CSV information not found")


def results(request):
    numin, numax = 200, 250

    lines = Linelist.objects.filter(nu__gte=numin, nu__lt=numax)
    c = {'lines': lines}
    return render(request, 'linelist/result.html', c)

def search(request):
    all_trans = Linelist.objects.all()

    trans_filter = TransFilter(request.GET, queryset=all_trans)

    c = {}
    c['filter'] = trans_filter
    filtered_trans = trans_filter.qs
    nresults = filtered_trans.count()

    querydict = request.GET
    c['querystring'] = '&' + querydict.urlencode()

    if request.GET:
        # Flag to trigger JavaScript to jump to search results.
        c['search_results'] = True
        c.update({'filtered_trans': filtered_trans, 'nresults': nresults})

    return render(request, 'linelist/search.html', c)

def download(request):
    all_trans = Linelist.objects.all()
    output_format = request.GET.get('format', 'csv')
    trans_filter = TransFilter(request.GET, queryset=all_trans)
    filtered_trans = trans_filter.qs
    if not filtered_trans:
        raise Http404

    return output_lines(output_format, filtered_trans)

def yield_csv_lines(filtered_trans):
    for trans in filtered_trans:
        yield f'{trans.to_csv()}\n'

def yield_json_lines(filtered_trans):
    ntrans = filtered_trans.count()
    yield '{"transitions": {'
    for i, trans in enumerate(filtered_trans):
        yield f'"{trans.id}": {trans.to_json()}'
        if i != ntrans-1:
            yield ','
    yield '}}'

def output_lines(output_format, filtered_trans):
    if output_format.lower() == 'csv':
        return StreamingHttpResponse(yield_csv_lines(filtered_trans),
                                     content_type='text/plain')
    elif output_format.lower() == 'json':
        return StreamingHttpResponse(yield_json_lines(filtered_trans),
                                     content_type='application/json')
