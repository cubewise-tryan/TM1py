import collections
import json
import sys

if sys.version[0] == '2':
    import httplib as http_client
else:
    import http.client as http_client

from TM1py.Objects import Server


def get_all_servers_from_adminhost(adminhost='localhost'):
    """ Ask Adminhost for TM1 Servers

    :param adminhost: IP or DNS Alias of the adminhost
    :return: List of Servers (instances of the TM1py.Server class)
    """

    conn = http_client.HTTPConnection(adminhost, 5895)
    request = '/api/v1/Servers'
    conn.request('GET', request, body='')
    response = conn.getresponse().read().decode('utf-8')
    response_as_dict = json.loads(response)
    servers = []
    for server_as_dict in response_as_dict['value']:
        server = Server(server_as_dict)
        servers.append(server)
    return servers


def read_cube_name_from_mdx(mdx):
    """ read the cubename from a valid MDX Query

    :param mdx: The MDX Query as String
    :return: String, name of a cube
    """

    mdx_trimed = ''.join(mdx.split()).upper()
    post_start = mdx_trimed.rfind("FROM[") + len("FROM[")
    pos_end = mdx_trimed.find("]WHERE", post_start)
    # if MDX has no dimension on titles
    if pos_end == 0:
        pos_end = len(mdx_trimed)-1
    cube_name = mdx_trimed[post_start:pos_end]
    return cube_name


def sort_addresstuple(dimension_order, unsorted_addresstuple):
    """ Sort the given mixed up addresstuple

    :param dimension_order: list of dimension names in correct order
    :param unsorted_addresstuple: list of Strings - ['[dim2].[elem4]','[dim1].[elem2]',...]

    :return:
        Tuple: ('[dim1].[elem2]','[dim2].[elem4]',...)
    """
    sorted_addresstupple = []
    for dimension in dimension_order:
        address_element = [item for item in unsorted_addresstuple if item.startswith('[' + dimension + '].')]
        sorted_addresstupple.append(address_element[0])
    return tuple(sorted_addresstupple)


def build_content_from_cellset(raw_cellset_as_dict, cell_properties, top):
    """ transform raw cellset data into concise dictionary

    :param raw_cellset_as_dict:
    :param cell_properties:
    :param top: Maximum Number of cells
    :return:
    """
    content_as_dict = CaseAndSpaceInsensitiveTuplesDict()

    cube_dimensions = [dim['Name'] for dim in raw_cellset_as_dict['Cube']['Dimensions']]

    axe0_as_dict = raw_cellset_as_dict['Axes'][0]
    axe1_as_dict = raw_cellset_as_dict['Axes'][1]

    ordinal_cells = 0

    ordinal_axe2 = 0
    # get coordinates on axe 2: Title
    # if there are no elements on axe 2 assign empty list to elements_on_axe2
    if len(raw_cellset_as_dict['Axes']) > 2:
        axe2_as_dict = raw_cellset_as_dict['Axes'][2]
        tuples_as_dict = axe2_as_dict['Tuples'][ordinal_axe2]['Members']
        elements_on_axe2 = [data['UniqueName'] for data in tuples_as_dict]
    else:
        elements_on_axe2 = []

    ordinal_axe1 = 0
    for i in range(axe1_as_dict['Cardinality']):
        # get coordinates on axe 1: Rows
        tuples_as_dict = axe1_as_dict['Tuples'][ordinal_axe1]['Members']
        elements_on_axe1 = [data['UniqueName'] for data in tuples_as_dict]
        ordinal_axe0 = 0
        for j in range(axe0_as_dict['Cardinality']):
            # get coordinates on axe 0: Columns
            tuples_as_dict = axe0_as_dict['Tuples'][ordinal_axe0]['Members']
            elements_on_axe0 = [data['UniqueName'] for data in tuples_as_dict]
            coordinates = elements_on_axe0 + elements_on_axe2 + elements_on_axe1
            coordinates_sorted = sort_addresstuple(cube_dimensions, coordinates)
            # get cell properties
            content_as_dict[coordinates_sorted] = {}
            for cell_property in cell_properties:
                value = raw_cellset_as_dict['Cells'][ordinal_cells][cell_property]
                content_as_dict[coordinates_sorted][cell_property] = value
            ordinal_axe0 += 1
            ordinal_cells += 1
            if top is not None and ordinal_cells >= top:
                break
        if top is not None and ordinal_cells >= top:
            break
        ordinal_axe1 += 1
    return content_as_dict


def build_pandas_dataframe_from_cellset(cellset):
    import pandas as pd

    cellset_clean = {}
    for coordinates, cell in cellset.items():
        coordinates_clean = tuple([unique_name[unique_name.rfind('].[',) + 3:-1] for unique_name in coordinates])
        cellset_clean[coordinates_clean] = cell['Value']

    dimension_names = tuple([unique_name[1:unique_name.find('].[')] for unique_name in coordinates])

    # create index
    keylist = list(cellset_clean.keys())
    multiindex = pd.MultiIndex.from_tuples(keylist, names=dimension_names)

    # create DataFrame
    values = list(cellset_clean.values())
    return pd.DataFrame(values, index=multiindex)


class CaseAndSpaceInsensitiveDict(collections.MutableMapping):
    """A case-and-space-insensitive dict-like object with String keys.

    Implements all methods and operations of
    ``collections.MutableMapping`` as well as dict's ``copy``. Also
    provides ``adjusted_items``, ``adjusted_keys``.

    All keys are expected to be strings. The structure remembers the
    case of the last key to be set, and ``iter(instance)``,
    ``keys()``, ``items()``, ``iterkeys()``, and ``iteritems()``
    will contain case-sensitive keys. 

    However, querying and contains testing is case insensitive:
        elements = TM1pyElementsDictionary()
        elements['Travel Expesnses'] = 100
        elements['travelexpenses'] == 100 # True

    Entries are ordered
    """

    def __init__(self, data=None, **kwargs):
        self._store = collections.OrderedDict()
        if data is None:
            data = {}
        self.update(data, **kwargs)

    def __setitem__(self, key, value):
        # Use the adjusted cased key for lookups, but store the actual
        # key alongside the value.
        self._store[key.lower().replace(' ', '')] = (key, value)

    def __getitem__(self, key):
        return self._store[key.lower().replace(' ', '')][1]

    def __delitem__(self, key):
        del self._store[key.lower().replace(' ', '')]

    def __iter__(self):
        return (casedkey for casedkey, mappedvalue in self._store.values())

    def __len__(self):
        return len(self._store)

    def adjusted_items(self):
        """Like iteritems(), but with all adjusted keys."""
        return (
            (adjusted_key, key_value[1])
            for (adjusted_key, key_value)
            in self._store.items()
        )

    def adjusted_keys(self):
        """Like keys(), but with all adjusted keys."""
        return (
            adjusted_key
            for (adjusted_key, key_value)
            in self._store.items()
        )

    def __eq__(self, other):
        if isinstance(other, collections.Mapping):
            other = CaseAndSpaceInsensitiveDict(other)
        else:
            return NotImplemented
        # Compare insensitively
        return dict(self.adjusted_items()) == dict(other.adjusted_items())

    # Copy is required
    def copy(self):
        return CaseAndSpaceInsensitiveDict(self._store.values())

    def __repr__(self):
        return str(dict(self.items()))


class CaseAndSpaceInsensitiveTuplesDict(collections.MutableMapping):
    """A case-and-space-insensitive dict-like object with String-Tuples Keys.

    Implements all methods and operations of
    ``collections.MutableMapping`` as well as dict's ``copy``. Also
    provides ``adjusted_items``, ``adjusted_keys``.

    All keys are expected to be tuples of strings. The structure remembers the
    case of the last key to be set, and ``iter(instance)``,
    ``keys()``, ``items()``, ``iterkeys()``, and ``iteritems()``
    will contain case-sensitive keys. 

    However, querying and contains testing is case insensitive:
        data = CaseAndSpaceInsensitiveTuplesDict()
        data[('[Business Unit].[UK]', '[Scenario].[Worst Case]')] = 1000
        data[('[BusinessUnit].[UK]', '[Scenario].[worstcase]')] == 1000 # True
        data[('[Business Unit].[UK]', '[Scenario].[Worst Case]')] == 1000 # True

    Entries are ordered
    """

    def __init__(self, data=None, **kwargs):
        self._store = collections.OrderedDict()
        if data is None:
            data = {}
        self.update(data, **kwargs)

    def __setitem__(self, key, value):
        # Use the adjusted cased key for lookups, but store the actual
        # key alongside the value.
        self._store[tuple([item.lower().replace(' ', '') for item in key])] = (key, value)

    def __getitem__(self, key):
        return self._store[tuple([item.lower().replace(' ', '') for item in key])][1]

    def __delitem__(self, key):
        del self._store[tuple([item.lower().replace(' ', '') for item in key])]

    def __iter__(self):
        return (casedkey for casedkey, mappedvalue in self._store.values())

    def __len__(self):
        return len(self._store)

    def adjusted_items(self):
        """Like iteritems(), but with all adjusted keys."""
        return (
            (adjusted_key, key_value[1])
            for (adjusted_key, key_value)
            in self._store.items()
        )

    def adjusted_keys(self):
        """Like keys(), but with all adjusted keys."""
        return (
            adjusted_key
            for (adjusted_key, key_value)
            in self._store.items()
        )

    def __eq__(self, other):
        if isinstance(other, collections.Mapping):
            other = CaseAndSpaceInsensitiveTuplesDict(other)
        else:
            return NotImplemented
        # Compare insensitively
        return dict(self.adjusted_items()) == dict(other.adjusted_items())

    # Copy is required
    def copy(self):
        return CaseAndSpaceInsensitiveTuplesDict(self._store.values())

    def __repr__(self):
        return str(dict(self.items()))