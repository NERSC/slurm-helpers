import numpy as np
import re


#Node-related functions and classes:
class nodecoords:

    #constructor
    def __init__(self,nodeid):

        if isinstance(nodeid,str):
            #this is the regular nodeid format:
            if nodeid.startswith("nid"):
                self.nodeid=nodeid
                self.nodeid_to_coords()
                self.coords_to_topostring()
            #this is the column-format:
            elif re.match(r"^c\d.*?\-\d.*?c\d.*?s\d.*?n\d.*$",nodeid):
                self.topostring=nodeid
                self.topostring_to_coords()
                self.coords_to_nodeid()
            else:
                print "Unknown format!"
                self.rowid=None
                self.slotid=None
                self.bladeid=None
                self.topostring=None
        elif isinstance(nodeid,tuple):
            if len(nodeid)==3:
                self.rowid=nodeid[0]
                self.cageid=self.rowid%3
                self.slotid=nodeid[1]
                self.bladeid=nodeid[2]
                #for convenience, also define a group-id
                self.groupid=(self.rowid-self.rowid%6)/6
                self.coords_to_nodeid()
                self.coords_to_topostring()
            else:
                print "Unknown format!"
        else:
            print "Unknown format!"


    #compute row-id, column-id as well as blad-id
    def nodeid_to_coords(self):
        #nodeid is usually a string such as: nid<XXXXX>. The column and row/group and chassis Id can be found out by some arithmetic:
        #split number from nid prefix:
        number=int(self.nodeid.split('nid')[1])

        #for getting the row number, subtract the mod64 part and then divide by 64
        self.rowid=(number-number%64)/64
        self.cageid=self.rowid%3

        #the slot id can be found by just taking the mod64 mod4 part
        self.slotid=(number%64)/4

        #now determine the position inside the slot: for that just mod out 4:
        self.bladeid=(number%64)%4

        #for convenience, also define a group-id
        self.groupid=(self.rowid-self.rowid%6)/6


    #get the column-row format string
    def coords_to_topostring(self):
        tmpcol1=(self.rowid-self.rowid%3)/3
        self.physrow=tmpcol1/12
        self.physcolumn=tmpcol1%12

        #create topostring
        self.topostring="c"+str(self.physcolumn)+"-"+str(self.physrow)+"c"+str(self.cageid)+"s"+str(self.slotid)+"n"+str(self.bladeid)


    #get coords from topostring
    def topostring_to_coords(self):
        #get slot and blade-id first
        self.slotid=int(re.search(r"s(\d.*?)n",self.topostring).groups()[0])
        self.bladeid=int(re.search(r"n(\d.*?)$",self.topostring).groups()[0])
        #compute rowid:
        self.physcolumn=int(re.search(r"^c(\d.*?)\-.*",self.topostring).groups()[0])
        self.physrow=int(re.search(r"^.*?\-(\d.*?)c.*",self.topostring).groups()[0])
        self.cageid=int(re.search(r"^.*?\-\d.*?c(\d.*?)s.*",self.topostring).groups()[0])
        self.rowid=self.cageid+3*(self.physcolumn+12*self.physrow)
        #groupid
        self.groupid=(self.rowid-self.rowid%6)/6


    #get nodeid from coords
    def coords_to_nodeid(self):
        self.nodeid="nid{num:05d}".format(num=self.bladeid+4*(self.slotid+16*self.rowid))


    #return mesh-coords
    def get_meshcoords(self):
        return self.rowid,self.slotid,self.bladeid


#read the nodelist file
def parse_nodelist_file(filename):
    with open(filename) as f:
        lines=f.readlines()
        f.close()

    nodelist=[]
    for line in lines:
        if re.match(".*?c\d.*?\-\d.*?c\d.*?s\d.*?n.*",line):
            tmpdict={}
            tmpdict['node_number']=int(line.split()[0])
            tmpdict['nid']="nid{num:05d}".format(num=tmpdict['node_number'])
            tmpdict['topostring']=line.split()[2]
            tmpdict['type']=line.split()[3]
            nodelist.append(tmpdict)

    #return the nodelist
    return nodelist


#parse nodeliststrings
def parse_nodeliststring(nodeliststring):
    tmpnodelist=[]
    if re.match(r'^nid.*?\[(.*?)\]$',nodeliststring):
        tmpnodelist=re.search(r'^nid.*?\[(.*?)\]$',nodeliststring).groups()[0].split(',')
    elif re.match(r'^nid\d{5}$',nodeliststring):
        tmpnodelist=[re.search(r'^nid(.*)$',nodeliststring).groups()[0]]
    else:
        #assume list of the format nidXXXXX,nidXXXXX,....
        nodelistsplit=nodeliststring.split(',')
        tmpnodelist=[]
        for string in nodelistsplit:
            search=re.search(r'^nid(.*)$',string)
            if not search:
                raise ValueError("Unknown Nodelist Format.")
            else:
                tmpnodelist.append(search.groups()[0])
    #expand the nodelist
    nodelist=[]
    for item in tmpnodelist:
        if "-" not in item:
            nodelist.append("nid{num:05d}".format(num=int(item)))
        else:
            low=int(item.split("-")[0])
            high=int(item.split("-")[1])+1
            for node in range(low,high):
                nodelist.append("nid{num:05d}".format(num=node))
    #return the final node list
    return nodelist
