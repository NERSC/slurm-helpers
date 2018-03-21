#!/usr/bin/env python

# for debugging:
from __future__ import print_function
import sys
def debug(s):
    return
    print(s, file=sys.stderr)

import re

import curses
class DFNodesView:
    """ A pan-able curses pad showing nodes of a DragonFly-topology cluster """
    
    def __init__(self, cluster, win_y, win_x, view_ysize, view_xsize):
        self._map_pad = None
        self._headings_row_pad = None 
        self._headings_col_pad = None 
        self._topcorner_pad = None
        
        # where on the terminal to draw this view:
        self._win_y = win_y
        self._win_x = win_x
        # where in the pad we are currently looking:
        self._viewport_y = 0
        self._viewport_x = 0
        self._view_ysize = view_ysize
        self._view_xsize = view_xsize
        
        # cluster must provide cluster.extents, a list with the extent of each
        # of the 6 building blocks (which will be drawn as x x y y y x, where
        # "x x" means a dimension drawn in x and packed ito the next dimension
        # also drawn in x), and a final entry which is the number of groups
        # in the cluster (since the final row may be incomplete)
        # Note that each extent is in units of "the extent before it", eg 
        # extent of a group is 2 (cabinets), extent of a row is 6 (groups)
        # exception is 'cluster' which is in units of 'groups'
        # cluster must also provide functions for address_from_nid, 
        # nodename_from_nid and nid_from_address
        assert len(cluster.extents) == 7
        self._cluster = cluster 
    
        # index of each extent by name, for sanity/readability:
        # note that we talk about rows and columns of groups, but we display
        # a row of groups as a column of text blocks. To minimize ambiguity, 
        # "row" and "col" refer to physcial location of groups in machine room,
        # while "char" and "line" refer to a display unit on the screen
        names = ['SLOT', 'CAGE', 'CABINET', 'GROUP', 'ROW', 'ROOM', 'CLUSTER']
        # hmm, slot_number vs pos_in_slot is confusing, causes errors
        self._dims = dict(zip(names, range(len(names))))
        
        # viewer might compact display by wrapping either long horizontal pad
        # or long vertical pad, leaving a gap to indicate the wrap:
        self._hwrapping = 1      # how many chunks a wide cluster is split into
        self._vwrapping = 1      # how many chunks a long cluster is split into
        self._wrap_gap_lines = 2 # vertical space between chunks 
        self._wrap_gap_chars = 4 # horizontal space between chunks 
        
        # useful shorthand for within this method:
        dims = self._dims
        extents = cluster.extents
        
        # how many (lines,chars) are used to display each building block:
        # slots has 1 char per node, plus 1 char space between slots:
        self._drawn_sz  = [ (1, extents[0] + 1) ]                # slot
        # cage/cabinet/group/row have 4-char gap between rows
        chars_per_group = self._drawn_sz[-1][1]*extents[1] + 4
        self._drawn_sz += [ (1, chars_per_group) ]               # cage
        self._drawn_sz += [ (extents[2], chars_per_group) ]      # cabinet
        # each group also has a line for label, and a space between groups:
        lines_per_group = extents[2]*extents[3] + 2 
        self._drawn_sz += [ (lines_per_group, chars_per_group) ] # group
        lines_per_row = extents[4]*lines_per_group 
        self._drawn_sz += [ (lines_per_row, chars_per_group) ]   # row
        chars_per_room = extents[5]*chars_per_group
        self._drawn_sz += [ (lines_per_row, chars_per_room) ]    # room
        
        # label formats for each building block
        self._labels = [ lambda slot: '{0:^{w}d}'.format(slot, w=extents[0]),
                         lambda cage: 'c{0:d}'.format(cage),
                         # cab label needs to know which group in row it is in
                         lambda cab,grp: 'c{0:d}-X'.format(cab + grp*extents[3]),
                         lambda grp: '',  # no label for group-in-row 
                         lambda row: 'cY-{0:d} (row {0:d})'.format(row),
                         # group-in-cluster uses global groupid, not pos in row
                         lambda gid: 'g{0:02d}'.format(gid) ] # global group id
        
        # the number of lines/chars to reserve for the header pads:
        self._hlines = 1
        # left-header has 2 parts, cabinet and cage:
        # how many cabinets in a row? last cab in grp and last grp in row:
        cab = extents[dims['GROUP']]-1
        grp = extents[dims['ROW']]-1
        self._hchars_cab = len(self._labels[dims['CABINET']](cab,grp)) + 2
        cage = extents[dims['CABINET']]-1
        self._hchars_cage = len(self._labels[dims['CAGE']](cage)) + 1
        self._hchars = self._hchars_cab + self._hchars_cage

        self.report = None
        self.colors = { 'N':0, 'H':1 } # normal, highlight
        #curses.init_pair(self.colors['N'], curses.COLOR_WHITE,  curses.COLOR_BLACK) # predefined default
        aaa = curses.init_pair(self.colors['H'], curses.COLOR_BLACK,  curses.COLOR_YELLOW)
        debug("color pair: " + str(aaa))

    def _wrapped_shape(self, hwraps, vwraps):
        """ used when deciding whether to wrap a long or wide display. Returns
            tuple of lines,chars,aspect_ratio of the cluster map with a wide 
            map wrapped hwraps times or a long one wrapped vwraps times (one of
            these must be 1, can't wrap in two dimensions simultaneously)
        """
        assert hwraps==1 or vwraps==1
        # how many groups must we have space for if we wrap?:
        extents = self._cluster.extents
        ngroups_long = -(-extents[self._dims['ROW']]//vwraps) * hwraps
        ngroups_wide = -(-extents[self._dims['ROOM']]//hwraps) * vwraps
        l,c = self._drawn_sz[self._dims['GROUP']]
        lines = l*ngroups_long + (hwraps-1)*self._wrap_gap_lines
        chars = c*ngroups_wide + (vwraps-1)*self._wrap_gap_chars
        return lines,chars,float(chars)/lines

    def resize_pad(self, view_ysize, view_xsize):
        
        #debug("resizing pad to {0},{1}".format(view_ysize, view_xsize))
        # for error checking:
        nrows = self._cluster.extents[self._dims['ROOM']]
        rowsize = self._cluster.extents[self._dims['ROW']]
        
        # is the resize viable?
        l,c = self._drawn_sz[self._dims['GROUP']]
        min_lines = l + self._hlines + 1
        min_chars = c + self._hchars + 1 
        if view_ysize < min_lines or view_xsize < min_chars:
            Exception("viewport is too small for even 1 group!")
        
        self._view_ysize = view_ysize
        self._view_xsize = view_xsize

        # is it better to wrap the display?
        res = 1.1 # resistance to wrapping - wrapping must be this much better 
                  # than not wrapping to be accepted
        viewport_ar = float(view_xsize)/view_ysize
        hwrapping,vwrapping = 1,1
        y,x,ar = self._wrapped_shape(hwrapping,vwrapping)
        #debug("x={0},y={1},ar={2} vs view_ysize={3}, view_xsize={4}".format(x,y,ar,view_ysize,view_xsize))
        if x > view_xsize and y < view_ysize and ar > viewport_ar:
            # cluster is wide compared to viewport, try increasing hwrapping
            while ar > viewport_ar:
                hwrapping += 1
                #debug("increasing hwrapping to " + str(hwrapping))
                y1,x1,ar1 = self._wrapped_shape(hwrapping,vwrapping)
                if abs(ar-viewport_ar) < abs(ar1-viewport_ar)*res:
                    # the previous wrapping was better, we've gone too far
                    hwrapping -= 1
                    #debug("decreasing hwrapping to " + str(hwrapping))
                    break
                else:
                    y,x,ar = y1,x1,ar1
                if hwrapping>nrows:
                    Exception("hwrapping failure: {0} > {1}".format(hwrapping,nrows)) 
        elif x < view_xsize and y > view_ysize and ar < viewport_ar:
            # cluster is long compared to viewport, try vwrapping
            while ar < viewport_ar:
                vwrapping += 1
                #debug("increasing vwrapping to " + str(hwrapping))
                y1,x1,ar1 = self._wrapped_shape(hwrapping,vwrapping)
                if abs(ar-viewport_ar) < abs(ar1-viewport_ar)*res:
                    # the previous wrapping was better, we've gone too far
                    vwrapping -= 1
                    #debug("decreasing hwrapping to " + str(hwrapping))
                    break
                else:
                    y,x,ar = y1,x1,ar1
                if vwrapping>rowsize:
                    Exception("vwrapping failure: {0} > {1}".format(vwrapping,rowsize)) 
        
        # does this resize actually change the pad size?
        if self._map_pad:
            if self._map_pad.getmaxyx() == (y,x):
                debug("map pad did not change size")
                self.refresh()
                return # nothing to do
            else:
                aaa = self._map_pad.getmaxyx()
                debug("map pad changed size to {0:d}, {1:d}".format(*aaa))
        
        # record the wrapping:
        self._hwrapping = hwrapping
        self._vwrapping = vwrapping
        
        # create/replace the pads. pads are arranged like:  
        #   CCXXXX
        #   YYMMMM
        #   YYMMMM
        debug("creating map pad size {0:d}, {1:d}".format(y,x))
        self._map_pad = curses.newpad(y+1,x+1)
        #debug("map size: {0} x {1}".format(y,x))
        self._headings_row_pad = curses.newpad(self._hlines, x)
        self._headings_col_pad = curses.newpad(y, self._hchars)
        self._topcorner_pad = curses.newpad(self._hlines, self._hchars)
        #debug("topcorner size: {0} x {1}".format(self._hlines, self._hchars))
        
        self.draw_frame()
        # then need to draw all of the currently-visible reports
        self.draw_report()
        # and finally, redraw the pads:
        self.refresh()

    def set_report(self, report):
        self.report = report

    def draw_report(self):
        if self.report:
            for nid,report in self.report.iteritems():
                y,x = self._node_yx(nid)
                debug('adding {0:s} with attr {1:d} for nid {4:d} at y={2:d}, x={3:d}'.format(report[0],self.colors[report[1]],y,x,nid))
                attr = curses.color_pair(self.colors[report[1]])
                self._map_pad.addch(y,x,report[0],attr)

    def refresh(self):
        #debug('refresh topcorner 0,0,{0},{1},{2},{3} with viewport {4},{5}'.format(self._win_y, self._win_x,self._hlines, self._hchars,view_ysize, view_xsize) )
        # noutrefresh args are pad top,left, then window top,left,height,width
        self._topcorner_pad.noutrefresh(0,0, self._win_y, self._win_x,
                                             self._hlines, self._hchars)
        self._headings_row_pad.noutrefresh(0, self._viewport_x,
                             self._win_y, self._win_x+self._hchars,
                             self._hlines, self._view_xsize-1)
        self._headings_col_pad.noutrefresh(self._viewport_y, 0,
                             self._win_y+self._hlines, self._win_x,
                             self._view_ysize-1, self._hchars) 
        self._map_pad.noutrefresh(self._viewport_y, self._viewport_x,
                             self._win_y+self._hlines, self._win_x+self._hchars, 
                             self._view_ysize-1, self._view_xsize-1)

    def _group_yx(self, group):
        """ return the y,x tuple for position on the map pad of the top left 
            symbol in the group (will be a label row)
        """
        # TODO consider memoizing this (via decorator) 
        extents = self._cluster.extents
        nrows = extents[self._dims['ROOM']]
        ncols = extents[self._dims['ROW']]
        row = group // nrows
        col = group % nrows
        # deal with wrapping:
        l_room,c_room = self._drawn_sz[self._dims['ROOM']]
        rows_per_block = -(-nrows//self._hwrapping)
        y0 = (row // rows_per_block)*(l_room+self._wrap_gap_lines)
        cols_per_block = -(-ncols//self._vwrapping)
        x0 = (col // cols_per_block)*(c_room+self._wrap_gap_chars)
        
        lgroup,cgroup = self._drawn_sz[self._dims['GROUP']]
        y = y0 + (col%cols_per_block)*lgroup
        x = x0 + (row%rows_per_block)*cgroup
        return y,x

    def _node_yx(self, nid):
        """ return the y,x tuple for position on map pad to draw node nid """
        addr = self._cluster.address_from_nid(nid)
        y,x = self._group_yx(addr[-1])
        debug("got group {0:d}, groupyx {1:d},{2:d}".format(addr[-1],y,x))
        y += 1                             # shift for group label
        l,c = self._drawn_sz[self._dims['CABINET']]
        y += l*addr[self._dims['GROUP']]   # shift for cabinet 
        l,c = self._drawn_sz[self._dims['CAGE']]
        y += l*addr[self._dims['CABINET']] # shift for cage
        l,c = self._drawn_sz[self._dims['SLOT']]
        x += c*addr[self._dims['CAGE']]    # shift for slot
        x += addr[self._dims['SLOT']]      # shift for node
        return y,x

    def draw_frame(self):
        """ draw the header pads, and the group labels """
        
        s = '{0:^{width}s}'.format('slot:', width=self._hchars-1)
        self._topcorner_pad.addstr(0,0,s,curses.A_BOLD)
        
        extents = self._cluster.extents
        # headers are repeated for wrapping, work out size of each block:
        l_slot,c_slot   = self._drawn_sz[self._dims['SLOT']]
        l_cage,c_cage   = self._drawn_sz[self._dims['CAGE']]
        l_cab,c_cab     = self._drawn_sz[self._dims['CABINET']]
        l_group,c_group = self._drawn_sz[self._dims['GROUP']]
        l_row,c_row     = self._drawn_sz[self._dims['ROW']]
        l_room,c_room   = self._drawn_sz[self._dims['ROOM']]
        l_wrap = l_room + self._wrap_gap_lines
        c_wrap = c_room + self._wrap_gap_chars
        
        # header row shows slot numbers, repeated for each group across
        label = self._labels[self._dims['SLOT']]  # lambda
        for wrap in range(self._vwrapping):
            x0 = wrap*c_wrap
            for row in range(extents[self._dims['ROOM']]//self._hwrapping): 
                x1 = x0 + row*c_row
                for slot in range(extents[self._dims['CAGE']]):
                    x = x1 + slot*c_slot
                    self._headings_row_pad.addstr(0,x,label(slot),curses.A_BOLD)
        
        # header col 
        cab_label = self._labels[self._dims['CABINET']]  # lambda
        cage_label = self._labels[self._dims['CAGE']]  # lambda
        for wrap in range(self._hwrapping):
            y0 = wrap*l_wrap
            for group in range(extents[self._dims['ROW']]//self._vwrapping):
                y1 = y0 + group*l_group + 1  # leave line for group label
                for cab in range(extents[self._dims['GROUP']]):
                    # draw cab label on left
                    y = y1 + cab*l_cab
                    s = cab_label(cab,group)
                    self._headings_col_pad.addstr(y,0,s,curses.A_BOLD)
                    x = self._hchars - self._hchars_cage
                    for cage in range(extents[self._dims['CABINET']]):
                        # draw cage label on right
                        y = y1 + cab*l_cab + cage*l_cage
                        s = cage_label(cage)
                        self._headings_col_pad.addstr(y,x,s,curses.A_BOLD)

        # group labels:
        for group in range(extents[self._dims['CLUSTER']]):
            y,x = self._group_yx(group)
            addr = [0]*len(extents) 
            addr[-1] = group
            first = self._cluster.nodename_from_address(addr)
            addr = [-1]*len(extents) 
            addr[-1] = group
            last = self._cluster.nodename_from_address(addr)
            row = group//extents[self._dims['ROOM']]
            label = self._labels[self._dims['ROW']](row)
            label += '{0:4s}g{1:02d}  '.format('',group)
            label += '  {0}..{1}'.format(first,last)
            self._map_pad.addstr(y,x,label,curses.A_BOLD)

    def pan(self,y_dist,x_dist):
        """ move the viewport so many lines and chars """
        self.pan_to(max(0,self._viewport_y + y_dist), 
                    max(0,self._viewport_x + x_dist))

    def pan_to(self,y,x):
        sz_y,sz_x,ar = self._wrapped_shape(self._hwrapping, self._vwrapping)
        self._viewport_y = y if y>=0 else sz_y-y
        self._viewport_x = x if x>=0 else sz_x-x
        self._viewport_y = min(self._viewport_y, sz_y-self._view_ysize+self._hlines)
        self._viewport_y = max(0,self._viewport_y)
        self._viewport_x = min(self._viewport_x, sz_x-self._view_xsize+self._hchars)
        self._viewport_x = max(0,self._viewport_x)
        self.refresh()


from operator import mul

class Cluster:
    """ stub class for testing """

    def __init__(self, extents):
        assert len(extents)==7
        self.extents = list(extents)
        
        # total address space enclosed at each rank (eg 4x16=64 nodes/cage)
        self.space = [reduce(mul, extents[:i]) for i in range(1,len(extents))]
        # all rows might not be full, so total nid-space is from num groups
        self.space.append(extents[-1]*self.space[3])

    def address_from_nid(self, nid):
        """ address is a tuple of distance into each dim of self.extents """
        address = list(self.space)
        address[6] = nid/self.space[3] # group in cluster
        nid -= address[6]*self.space[3]
        address[3] = nid/self.space[2] # cabinet in group 
        nid -= address[3]*self.space[2]
        address[2] = nid/self.space[1] # cage in cabinet
        nid -= address[2]*self.space[1]
        address[1] = nid/self.space[0] # slot in cage 
        nid -= address[1]*self.space[0]
        address[0] = nid%self.extents[0] 
        address[5] = address[6]%self.extents[5] # row
        address[4] = address[6]/self.extents[4] # group_in_row
        return address

    def nid_from_address(self, address):
        """ address is a tuple of distance into each dim of self.extents,
            and nid is the manhattan distance to that address. Negative
            elements of address are treated as "distance backwards".
            If address includes group-in-cluster (last element) then row and 
            column are ignored, else group is calculated from row and column
        """
        # handle negative elements of address:
        dist = lambda i,addr: addr[i] + (0 if addr[i]>=0 else self.extents[i])

        if len(address) == len(self.extents):
            grp = address[-1]
        else:
            grp = address[5]*self.extents[5] + address[4]
        nid=dist(0,address)
        for i in 1,2,3:
            nid += dist(i,address)*self.space[i-1]
        nid += grp*self.space[3]
        return nid

    def nodename_from_address(self, address):
        """ address is a tuple of distance into each dim of self.extents.
            Negative elements of address are treated as "distance backwards"
        """
        nid = self.nid_from_address(address)
        return 'nid{0:05d}'.format(nid)


def parse_nodelist(nlist_as_text):
    """ generator to translate slurm nodelists like nid0[1-15,17,18] into node names """
    prefix, sep, list = nlist_as_text.partition('[')
    if sep:
        for member in list.rstrip(']').split(','):
            first,sep1,last = member.partition('-')
            if sep1:
                for i in range(int(first),int(last)+1):
                    try:
                        yield 'nid{0:05d}'.format(i)
                    except:
                        debug("error with " + member + " (i="+str(i)+")")
                        raise
            else:
                #yield prefix + first
                yield 'nid{0:05d}'.format(int(first))
    else:
        yield prefix


from time import ctime
import getopt
import subprocess
import os
def main(stdscr):

    # reports to generate:
    # my immediate need is to look at nodes in a reservation
    usage = "show info on a cluster map"
    usage += sys.argv[0] + "-r res "
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'r:', ['res'])
    except getopt.GetoptError:
        print(usage)
        sys.exit(2)

    res = None
    for opt in opts:
        if opt[0] in ('-r', '--res'):
            res = opt[1]
        else:
            print(usage)
            sys.exit(2)

    # --- hacky code ---
    # generate reports I care about
    # start simple with specifics I want: which nodes is a reservation for?
    # bottom layer is nodes-by-type/state: . for down, + for hsw and * for knl
    # layer above is a highlight on nodes for the reservation
    import subprocess
    scontrol = subprocess.Popen('scontrol -a -o show node'.split(), stdout=subprocess.PIPE)
    nodereport,err = scontrol.communicate()
    report = {} # nid: char, attr_tag ('N' for normal or 'H' for highlight) 
    field_re = re.compile('(?:\A| )(?:\w+)=')
    for node in nodereport.splitlines():
      try:
        # fields are like "nodename=abcde" .. but the value can contain spaces or '='
        # characters, so we need to carefully parse the line:
        keys = [ k[:-1].strip() for k in field_re.findall(node) ]
        values = field_re.split(node)[1:]
        d = dict(zip(keys,values))
        # Handle spaces in optional final field "Reason" (for eg DOWN state):
        #d = dict(f.split('=',1) for f in node.partition(' Reason=')[0].split())
        nid = int(d['NodeName'].lstrip('nid'))
        if d['State'].startswith('D'):
            rep = '.'
        elif 'knl' in d.get('ActiveFeatures',''):
            rep = '*'
        else:
            rep = '+'
        report[nid] = [ rep, 'N' ]
      except:
        print("error parsing: \n" + node, file=sys.stderr)
        raise
    if res:
        cmd = 'scontrol -a -o show res'.split()
        cmd.append(res)
        scontrol = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        resreport,err = scontrol.communicate()
        d = dict(f.split('=',1) for f in resreport.split())
        for n in parse_nodelist(d['Nodes']):
            nid = int(n.lstrip('nid'))
            #debug("got nid {0:d} from {1:s}".format(nid,n))
            report[nid][1] = 'H'
        debug(str(report))
   
    # --- end hacky code ---

    if os.getenv("NERSC_HOST") == 'edison':
        cluster = Cluster([4, 16, 3, 2, 4, 4, 16])
    else:  # cori
        cluster = Cluster([4, 16, 3, 2, 6, 6, 34])

    term_height, term_width = stdscr.getmaxyx()
    viewer = DFNodesView(cluster, 0, 0, term_height, term_width)
    viewer.set_report(report)

    key = curses.KEY_RESIZE
    stdscr.clear()
    stdscr.refresh()
    while True:
        if key in (ord('q'), ord('Q')):
            break
        elif key == curses.KEY_RESIZE:
            term_height, term_width = stdscr.getmaxyx()
            viewer.resize_pad(term_height, term_width)
        elif key == curses.KEY_SLEFT:
            viewer.pan(0,-4)
        elif key == curses.KEY_SRIGHT:
            viewer.pan(0,4)
        elif key == 337: # magic number for shift-up (is this portable?)
            viewer.pan(-4,0)
        elif key == 336: # magic number for shift-down (is this portable?)
            viewer.pan(4,0)
        elif key == curses.KEY_HOME:
            viewer.pan_to(0,0)
        elif key == curses.KEY_END:
            viewer.pan_to(-1,-1)
        else: 
            # curses seems to handle term resize badly, get a second key hit 
            # registered but getch returns -1, and the screen breaks. Calling
            # noutrefresh on the various windows seems to fix it:
            viewer.refresh()
        
        # last:
        curses.doupdate()
        key = stdscr.getch()
        #debug ("got a new key at "+str(key) + " at " +ctime())


if __name__ == "__main__":
    curses.wrapper(main) 

