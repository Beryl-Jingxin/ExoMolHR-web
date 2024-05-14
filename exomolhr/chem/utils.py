MOLECULE_TYPE_TAGS = ['metal hydride', 'other hydride', 'metal oxide',
                      'other oxide', 'triatomic molecule', 'larger molecule',
                      'ion', 'other diatomic', 'atom']

def categorise_molecules(molecules):
    molecule_types = {}
    for molecule_type_tag in MOLECULE_TYPE_TAGS:
        molecule_types[molecule_type_tag + 's'] = molecules.filter(
                                    tags__name__in=[molecule_type_tag])
    return molecule_types

