from django.shortcuts import render, redirect
from django.http import Http404, StreamingHttpResponse, HttpResponse, FileResponse, HttpResponseRedirect
from django.views.generic import View
from django.urls import reverse
from django.forms.models import model_to_dict

from .models import Linelists
from .filters import TransFilters
# from chem.models import Molecule, Isotopologue
from pyvalem.formula import Formula
import os, csv, sqlite3
import pandas as pd


# Create your views here.

# con = sqlite3.connect('/home/jingxin/ExoMolHR-web/exomolhr/db.sqlite3', check_same_thread=False)
# db = con.cursor()
pieces_df = pd.read_csv('~/ExoMolHR-web/res/exomolhr.csv', header=0)

def molecules(request):
    molecules_colnames = ['molid', 'molecule', 'molhtml', 'moltag', 'molname', 'molmass']
    molecule_df = pd.read_csv('~/ExoMolHR-web/res/molecules.csv', header=0, names=molecules_colnames)
    context = {
        'columns': molecule_df.columns, 
        'rows': molecule_df.to_dict('records')}   
    return render(request, 'calculate/molecules.html', context)


def select_molecules(request):
    if request.method == 'POST':
        selected_molecules = request.POST.getlist('selected_molecules')
    if selected_molecules:
        # Concatenate the selected molecules to form the URL
        molecules_url = '_'.join(selected_molecules)
        if molecules_url:   
            return redirect(request,'calculate/isotopologues.html',molecules_url=molecules_url)


def isotopologues(request, molecules_url):
    selected_molecules = molecules_url.split('_')
    isotopologues_df = pieces_df[pieces_df['molecule'].isin(selected_molecules)]
    isotopologues_df = isotopologues_df[['molecule', 'molhtml', 'molname', 'isoslug', 'isoformula', 
                                         'isohtml', 'isotag', 'isomass']].drop_duplicates()
    isotopologues_df['id'] = isotopologues_df.reset_index().index+1
    # molecules_url = '_'.join(isotopologues_df['molecule'].drop_duplicates().values)
    moleculeshtml = ', '.join(list(isotopologues_df['molhtml'].unique()))
    context = {'columns': isotopologues_df.columns, 
               'rows': isotopologues_df.to_dict('records'), 
               'molecules_url': molecules_url,
               'moleculeshtml': moleculeshtml
               } 
    return render(request, 'calculate/isotopologues.html', context)


def select_isotopologues(request):
    if request.method == 'POST':
        selected_isotopologues = request.POST.getlist('selected_isotopologues')
    if selected_isotopologues:
        # Concatenate the selected isotopologues to form the URL
        isotopologues_url = '_'.join(selected_isotopologues)
        if isotopologues_url:   
            return redirect(request,'calculate/datasets.html',isotopologues_url=isotopologues_url)


def datasets(request, molecules_url, isotopologues_url):
    selected_molecules = molecules_url.split('_')
    selected_isotopologues = isotopologues_url.split('_')
    datasets_df = pieces_df[pieces_df[['molecule']].isin(selected_molecules).all(axis=1)]
    datasets_df = datasets_df[datasets_df[['isoslug']].isin(selected_isotopologues).all(axis=1)]
    datasets_df = datasets_df[['molecule', 'molhtml', 'molname', 
                               'isoslug', 'isoformula', 'isohtml', 'isotag', 'isomass',
                               'dataset', 'filename']].drop_duplicates()
    datasets_df['id'] = datasets_df.reset_index().index+1   
    # molecules_url = '_'.join(datasets_df['molecule'].drop_duplicates().values)
    # isotopologues_url = '_'.join(datasets_df['isoslug'].drop_duplicates().values)
    moleculeshtml = ', '.join(list(datasets_df['molhtml'].unique()))
    isotopologueshtml = ', '.join(list(datasets_df['isohtml'].unique())) 
    datasetshtml = ', '.join(list(datasets_df['dataset'].unique())) 
    context = {'columns': datasets_df.columns, 
               'rows': datasets_df.to_dict('records'), 
               'molecules_url': molecules_url,
               'isotopologues_url': isotopologues_url,
               'moleculeshtml': moleculeshtml,
               'isotopologueshtml': isotopologueshtml,
               'datasetshtml': datasetshtml
               }   
    return render(request, 'calculate/datasets.html', context)

        
def select_datasets(request):
    if request.method == 'POST':
        selected_datasets = request.POST.getlist('selected_datasets')
    if selected_datasets:
        # Concatenate the selected datasets to form the URL
        datasets_url = '_'.join(selected_datasets)
        if datasets_url:   
            return redirect(request,'calculate/dofilters.html',datasets_url=datasets_url)


def dofilters(request, molecules_url, isotopologues_url, datasets_url):
    selected_molecules = molecules_url.split('_')
    selected_isotopologues = isotopologues_url.split('_')
    selected_datasets = datasets_url.split('_')
    filters_df = pieces_df[pieces_df[['molecule']].isin(selected_molecules).all(axis=1)]
    filters_df = filters_df[filters_df[['isoslug']].isin(selected_isotopologues).all(axis=1)]    
    filters_df = filters_df[filters_df[['dataset']].isin(selected_datasets).all(axis=1)]   
    # Get column names matching the pattern 'xxx.a'
    columns_to_drop = filters_df.columns[filters_df.columns.str.match(r'[a-zA-Z]+\.\d+')]
    # Drop columns that match the pattern
    filters_df = filters_df.drop(columns=columns_to_drop)
    filters_df['id'] = filters_df.reset_index().index+1
    # molecules_url = '_'.join(filters_df['molecule'].drop_duplicates().values)
    # isotopologues_url = '_'.join(filters_df['isoslug'].drop_duplicates().values)
    # datasets_url = '_'.join(filters_df['dataset'].drop_duplicates().values)
    moleculeshtml = ', '.join(list(filters_df['molhtml'].unique()))
    isotopologueshtml = ', '.join(list(filters_df['isohtml'].unique())) 
    datasetshtml = ', '.join(list(filters_df['dataset'].unique())) 
    filenames = ', '.join(list(filters_df['filename'].unique()))
    context = {'columns': filters_df.columns,
               'rows': filters_df.to_dict('records'), 
               'molecules_url': molecules_url,
               'isotopologues_url': isotopologues_url,
               'datasets_url': datasets_url,
               'moleculeshtml': moleculeshtml,
               'isotopologueshtml': isotopologueshtml,
               'datasetshtml': datasetshtml,
               'filenames': filenames
               }  
    return render(request, 'calculate/dofilters.html', context)




def filters_old(request, molecule, isotopologue, dataset):
    csvinf_df = pieces_df[pieces_df[['molecule', 'isoslug']].isin([molecule, isotopologue, dataset]).all(axis=1)]
    localcsv_filename = csvinf_df['filename'].values[0]
    localcsv_filepath = '/home/jingxin/data/exomolhr/loc_result/'+localcsv_filename
    # Read the CSV file into a pandas DataFrame
    csv_df = pd.read_csv(localcsv_filepath, dtype=str).head(200)
    headers = [col.replace('Sigma','Σ').replace('Lambda','Λ').replace('Omega','Ω') for col in csv_df.columns]
    out = csv_df.to_dict('records')
    molhtml = csvinf_df['molhtml'].values[0]
    isohtml = csvinf_df['isohtml'].values[0]
    context = {'data': out, 
               'headers':headers,
               'molf': molecule, 
               'molh': molhtml, 
               'isos': isotopologue, 
               'isoh': isohtml,
               'ds': dataset}  
    return render(request, 'calculate/filters.html', context)


def download_localfile(request, molecule, isotopologue, dataset):
    # Define the path to the file you want to download
    csvinf_df = pieces_df[pieces_df[['molecule', 'isoslug']].isin([molecule, isotopologue, dataset]).all(axis=1)]
    if not csvinf_df.empty:
        localcsv_filename = csvinf_df.iloc[0]['filename']
        localcsv_filepath = '/home/jingxin/data/exomolhr/loc_result/' + localcsv_filename
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

    lines = Linelists.objects.filter(nu__gte=numin, nu__lt=numax)
    c = {'lines': lines}
    return render(request, 'linelist/result.html', c)

def search(request):
    all_trans = Linelists.objects.all()

    trans_filter = TransFilters(request.GET, queryset=all_trans)

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
    all_trans = Linelists.objects.all()
    output_format = request.GET.get('format', 'csv')
    trans_filter = TransFilters(request.GET, queryset=all_trans)
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
