from django.shortcuts import render, redirect
from django.http import Http404, StreamingHttpResponse, HttpResponse, FileResponse, HttpResponseRedirect
from django.views.generic import View
from django.urls import reverse
from django.forms.models import model_to_dict

from django.conf import settings

from .models import Linelists
from .filters import TransFilters
# from chem.models import Molecule, Isotopologue
from pyvalem.formula import Formula
import os, csv, sqlite3
import pandas as pd


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


def get_data(request):
    print(request.GET)
    return











# XN WROTE THIS vvvvv
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
