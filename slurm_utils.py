#!/usr/bin/env python

import string
import re
def expand_nodelist(nlist):
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

class CrayXC:
    """ A Cray XC maps nodenames ("nid00123") to addresses (row, column,
        cage (ie chassis), slot (ie blade), node). From this we get a 
        "cname" like:  c{col:d}-{row:d}c{cage:d}s{slot:d}n{node:d} 
        (eg c2-0c1s2n3). Note that to get the dragonfly group, the column
        address needs to be decomposed into (group, cabinet). My original 
        purpose for this class is/was to support drawing the dragonfly 
        topology in a spatially-meaningful manner, so I'm more interested in
        (cabinet, group) than (column), and the address here is cast as a
        nest of dimensions from node-in-slot to row-in-room, with col-in-row
        decomposed into (cab-in-group, group-in-row), then the column address
        appended as a derived component.
    """

    dim_names = [ 'nodes_per_slot',    # SLOT
                  'slots_per_cage',    # CAGE
                  'cages_per_cab',     # CAB
                  'cabs_per_group',    # GROUP
                  'groups_per_row',    # ROW
                  'rows_in_room',      # ROOM
                  'cols_in_row'   ]    # derived from cab & group
    # make it easy to get the index of a dim by its name:
    _dims = ['node',
             'slot',
             'cage',
             'cab',
             'group',
             'row',
             'col' ]
    dims = (lambda d: {name: d.index(name) for name in d})(_dims) 
    # constants for dims (col is special and so lowercase)
    SLOT,CAGE,CAB,GROUP,ROW,ROOM,col = range(len(dims))

    def __init__(self, extents):
        """ describe a Cray XC cluster in terms of the extents of each rank
            in it's Dragonfly topology. Extents should correspond with CrayXC.dim_names.
            Some example extents are: 
                cori:   [4, 16, 3, 2, 6, 6]
                edison: [4, 16, 3, 2, 4, 4]
        """
        assert len(extents)==len(self.dims)-1 # don't pass col, we calculate it
        self.extents = list(extents) + [ extents[self.GROUP]*extents[self.ROW] ]
        # total address space enclosed at each rank (eg 4x16=64 nodes/cage)
        self.space = [reduce(mul, extents[:i]) for i in range(1,len(extents)+1)]
        self.space += [ self.space[self.CAB] ] # column is special

    def address_from_nid(self, nid):
        """ address is a tuple of distance into each dim of self.extents """
        address = list(self.space)
        for dim in range(self.ROOM,0,-1):
            address[dim] = nid // self.space[dim-1]
            nid -= address[dim]*self.space[dim-1]
        address[self.SLOT] = nid
        # col is special, it is the col number, not the distance into the column:
        address[self.col] = address[self.ROW]*self.extents[self.GROUP]+address[self.GROUP]
        return address

    def nid_from_address(self, address):
        assert (len(address)==len(self.dims))
        nid = address[0]
        for dim in range(self.ROOM):
            nid += address[dim+1]*self.space[dim]
        return nid

    _cname_fmt = 'c{{{col}}}-{{{row}}}c{{{cage}}}s{{{slot}}}n{{{node}}}'.format(**dims)
    def cname_from_address(self, address):
        return self._cname_fmt.format(*address)

    _re_address = re.compile('c(?P<col>\d+)-(?P<row>\d+)c(?P<cage>\d+)s(?P<slot>\d+)n(?P<node>\d+)')
    def address_from_cname(self, cname):
        match = self._re_address.search(cname)
        address = [ int(match.group(g)) for g in ['node', 'slot', 'cage' ] ]
        col = int(match.group('col'))
        group = col // self.extents[self.GROUP]
        cab = col % self.extents[self.GROUP]
        address += [ cab, group, int(match.group('row')), col ]
        return address


import unittest
import re
class TestCrayXC(unittest.TestCase):

    def setUp(self):
        self.cori = CrayXC([4,16,3,2,6,6])
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
