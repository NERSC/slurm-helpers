#!/usr/bin/env python3

# system python 3 on Cori is broken so user will need to load a
# python module, which will be 3.6+ anyway, so we'll take advantage
# of some of python's modern features:
import sys
if sys.version_info[0] < 3 or sys.version_info[1] < 5:
    print(sys.version_info)
    raise Exception("Requires python 3.5+ .. try\nmodule load python/3.6-anaconda-4.4")

_cluster = None
def init(nodes_per_slot=4, slots_per_cage=16, cages_per_cab=3, 
         cabs_per_group=2, groups_per_row=1, rows=1):
    global _cluster
    _cluster = CrayXC(extents={'slot':nodes_per_slot, 
                               'cage':slots_per_cage, 
                               'cab':cages_per_cab,
                               'group':cabs_per_group, 
                               'row':groups_per_row, 
                               'room':rows})

def nodename_to_cname(nodename):
    if _cluster is None:
        raise Exception("Need a cluster definition!")
    return _cluster.cname_from_nodename(nodename)

def cname_to_nodename(cname):
    if _cluster is None:
        raise Exception("Need a cluster definition!")
    return _cluster.nodename_from_cname(cname)

def nodelist_to_cnames(nlist: str):
    if _cluster is None:
        raise Exception("Need a cluster definition!")
    cnames = []
    for name in expand_nodelist(nlist):
        cnames.append(_cluster.cname_from_nodename(nodename))
    return cnames
    

    
    

import string
import re
def expand_nodelist(nlist: str, as_list=False) -> str:
    """ translate a nodelist like 'nid[02516-02575,02580-02635,02836]' into a 
        list of explicitly-named nodes, eg 'nid02516 nid02517 ...'
    """
    nodes = []
    if nlist.count('[') != nlist.count(']'):
        raise Exception("Incomplete nodelist: {}".format(nlist))
    prefix, sep0, nl = nlist.partition('[')
    if sep0:
        for component in nl.rstrip(']').split(','): 
            first,sep1,last = component.partition('-')
            width='0{:d}'.format(len(first))
            if sep1:
                nodes += [ '{0:s}{2:{1:s}d}'.format(prefix,width,i) 
                            for i in range(int(first),int(last)+1) ]
            else:
                nodes += [ '{0:s}{2:{1:s}d}'.format(prefix,width,int(first)) ] 
    else:
        nodes += [ prefix ]
    if as_list:
        return nodes
    else:
        return ' '.join(nodes)

import unittest
class TestExpandNodelist(unittest.TestCase):
    
    def test_expandnodelist(self):
        # slightly arbitrary list of test cases:
        nlist = 'nid02085'
        self.assertEqual(expand_nodelist(nlist), 'nid02085')
        nlist = 'nid00[200,222]'
        self.assertEqual(expand_nodelist(nlist), 'nid00200 nid00222')
        nlist = 'nid00[187-188]'
        self.assertEqual(expand_nodelist(nlist), 'nid00187 nid00188')
        nlist = 'nid00[189-191,193-195,200-203,208-229]'
        self.assertEqual(len(expand_nodelist(nlist).split()), 32)
        nlist = 'nid0[1299-1306,1309-1315,1317,1319-1334]'
        self.assertEqual(len(expand_nodelist(nlist).split()), 32)
        nlist = 'nid[10436-10439,10441-10443,10448-10452,10454-10511,10516-10535]'
        self.assertEqual(len(expand_nodelist(nlist).split()), 90)
        # incomplete nodelist should throw an exception:
        nlist = 'nid[07575,08812,09507,09637,09946,10361,10436,109'
        with self.assertRaises(Exception):
            expand_nodelist(nlist)


from operator import mul
import re

from typing import Dict
DimsMap = Dict[str,int]

class CrayXC:
    """ A Cray XC maps nodenames ("nid00123") to addresses (dicts 
        with the node, slot, cage, cabinet, group and row). From 
        cabinet and group we can calculate the "column", ie 
        cabinet-in-row, which is used in the cname. This class 
        uses the extents of each "dimension" of the cluster to 
        provide conversion between nids, cnames, addresses and 
        nodenames
    """
    # spaces and dims are basically the same, but used differently:
    # extents are "size of a space" but address is "position in each dimension",
    # so we provide two lists of these so different uses can use a sensible
    # set of names:
    spaces = ['slot', 'cage', 'cab', 'group', 'row', 'room' ]
    dims = ['node'] + spaces[:-1]

    def __init__(self, extents: DimsMap):
        """ describe a Cray XC cluster in terms of the extents of each rank
            in it's Dragonfly topology. Extents should correspond with CrayXC.dim_names.
            Some example extents are: 
                cori:   {'slot':4, 'cage':16, 'cab':3, 'group':2, 'row':6, 'room':6}
                edison: {'slot':4, 'cage':16, 'cab':3, 'group':2, 'row':4, 'room':4}
        """
        for d in self.spaces:
            assert d in extents
        self.extents = dict(extents)
        # total address space enclosed at each rank (eg 4x16=64 nodes/cage)
        space = 1
        self.space = {}
        for d in self.spaces:
            space *= extents[d]
            self.space[d] = space
        # for convenience:
        self.space['node'] = 1
        self.extents['node'] = 1

    def address_from_nid(self, nid: int, withcol: bool = False) -> DimsMap:
        """ address is dict with which node, slot, cage, etc """
        address = {}
        for dim in self.dims[-1::-1]:
            address[dim] = nid // self.space[dim]
            nid -= address[dim]*self.space[dim]
        if withcol:
            address['col'] = address['group']*self.extents['group']+address['cab']
        #print(address)
        return address

    def nid_from_address(self, address: DimsMap) -> int:
        nid=0
        if len(address)==1 and 'col' in address:
            address['group'] = address['col'] // self.extents['group']
            address['cab']   = address['col'] % self.extents['group']
        for dim in self.dims:
            nid += address.get(dim,0)*self.space[dim]
        return nid

    _cname_fmt = 'c{col}-{row}c{cage}s{slot}n{node}'
    def cname_from_address(self, address: DimsMap) -> str:
        if not 'col' in address:
            withcol = {'col':address.get('group',0)*self.extents['group']+address.get('cab',0)}
            address = dict(withcol, **address)
        return self._cname_fmt.format(**address)

    _re_address = re.compile('c(?P<col>\d+)-(?P<row>\d+)c(?P<cage>\d+)s(?P<slot>\d+)n(?P<node>\d+)')
    def address_from_cname(self, cname: str) -> DimsMap:
        match = self._re_address.search(cname)
        address = { dim: int(val) for dim,val in match.groupdict().items() }
        address['group'] = address['col'] // self.extents['group']
        address['cab']   = address['col'] % self.extents['group']
        return address

    def nid_from_nodename(self, nodename):
        """ nodenames are in format nid00000 """
        return int(nodename[3:])

    def nodename_from_nid(self, nid):
        """ nodenames are in format nid00000 """
        return 'nid{:05d}'.format(nid)

    def nodename_from_address(self, address: DimsMap) -> str:
        return self.nodename_from_nid(self.nid_from_address(address))

    def address_from_nodename(self, nodename: str) -> DimsMap:
        return self.address_from_nid(self.nid_from_nodename(nodename))

    def cname_from_nodename(self, nodename: str) -> str:
        addr = self.address_from_nid(self.nid_from_nodename(nodename))
        return self.cname_from_address(addr)

    def nodename_from_cname(self, cname: str) -> str:
        addr = self.address_from_cname(self, cname)
        return self.nodename_from_nid(self.nid_from_address(addr))


import unittest
import re
class TestCrayXC(unittest.TestCase):
    
    def setUp(self):
        self.cori = CrayXC(extents={'slot':4, 'cage':16, 'cab':3, 
                                    'group':2, 'row':6, 'room':6})

        # some corresponding nids and cnames:
        self.names  =  [ 'nid00005',   'nid00103',   'nid00739',   'nid01522' ]
        self.cnames =  [ 'c0-0c0s1n1', 'c0-0c1s9n3', 'c3-0c2s8n3', 'c7-0c2s12n2' ]
        self.names +=  [ 'nid03400',   'nid06676',    'nid09472',   'nid10792' ]
        self.cnames += [ 'c5-1c2s2n0', 'c10-2c2s5n0', 'c1-4c1s0n0', 'c8-4c0s10n0' ]
        self.names +=  [ 'nid13055' ,   'nid00000' ]
        self.cnames +=  [ 'c7-5c2s15n3', 'c0-0c0s0n0' ]
        self.nids = [ int(n[3:]) for n in self.names ]

    def test_address_from_nid(self):
        for pair in zip(self.nids, self.cnames):
            address = self.cori.address_from_nid(pair[0])
            self.assertEqual(self.cori.cname_from_address(address), pair[1])

    def test_nid_from_address(self):
        for pair in zip(self.nids, self.cnames):
            address = self.cori.address_from_cname(pair[1])
            nid = self.cori.nid_from_address(address)
            self.assertEqual(nid, pair[0])


if __name__ == '__main__':
    unittest.main()
