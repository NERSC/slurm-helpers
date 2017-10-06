#!/usr/bin/env python

def expand_nodelist(nlist):
    """ translate a nodelist like 'nid[02516-02575,02580-02635,02836]' into a 
        list of explicitly-named nodes, eg 'nid02516 nid02517 ...'
    """
    nodes = []
    prefix, sep0, nl = nlist.partition('[')
    if sep0:
        for component in nl.rstrip(']').split(','): 
            first,sep1,last = component.partition('-')
            if sep1:
                nodes += [ 'nid{:05d}'.format(i) for i in range(int(first),int(last)+1) ]
            else:
                nodes += [ 'nid{:05d}'.format(int(first)) ]
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
        # TODO: sensible response in presence of broken nodelist would be good:
        #nlist = 'nid[07575,08812,09507,09637,09946,10361,10436,109'

if __name__ == '__main__':
    unittest.main()
