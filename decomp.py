import numpy as np
import cray_helpers as ch
import argparse
import re


parser = argparse.ArgumentParser(description='Manipulate Nodelist returned by SLURM_JOB_NODELIST and other SLURM related tools.')
parser.add_argument('--list', metavar='-L', type=str, nargs=1, help='the actual list of nodes as returned by SLURM')
parser.add_argument('--decompose', metavar='-d', type=str, nargs=1, help='specify decomposition. supported are even-odd, rows, columns, random')
args = parser.parse_args()

#store the nodelist
nodeliststring=args.list[0]
decompstring=args.decompose[0]

#parse the nodeliststring
nodelist=ch.parse_nodeliststring(nodeliststring)

decomposition={}
if decompstring=="sorted":
    #just sort the nodelist:
    nodelist.sort()
    decomposition={'sorted':nodelist}
elif decompstring=="even-odd":
    #simple case, only two states
    decomposition={"even": [], "odd": []}
    for node in nodelist:
        coords=ch.nodecoords(node).get_meshcoords()
        index=coords[2]+4*(coords[1]+16*coords[0])
        if index%2==0:
            decomposition["even"].append(node)
        else:
            decomposition["odd"].append(node)
elif decompstring=="rows":
    #gather a dictionary of rows:
    decomposition={}
    for node in nodelist:
        coords=ch.nodecoords(node).get_meshcoords()
        rowname="row_{num:03d}".format(num=coords[0])
        if rowname in decomposition.keys():
            decomposition[rowname].append(node)
        else:
            decomposition[rowname]=[node]
elif decompstring=="columns":
    #gather a dictionary of rows:
    decomposition={}
    for node in nodelist:
        coords=ch.nodecoords(node).get_meshcoords()
        colname="col_{num:02d}".format(num=coords[1])
        if colname in decomposition.keys():
            decomposition[colname].append(node)
        else:
            decomposition[colname]=[node]
elif decompstring.startswith("block"):
    #check for the block extent:
    extents=re.search('^block\((.*?),(.*)\)',decompstring)
    if not extents:
        raise ValueError("Please specify block dims, i.e. block(numrows,numcols).")
    numrows=int(extents.groups()[0])
    numcols=int(extents.groups()[1])
    if (numcols>64) or (numrows>6):
        raise ValueError("The block size cannot be bigger than (6,64)")

    #first, get all groups involved:
    nodelist.sort()
    groups=set()
    for node in nodelist:
        nodecoords=ch.nodecoords(node)
        groups.add(nodecoords.groupid)
    groups=list(groups)
    #now, scan through the group with a numrows,numcols filter view
    numgroups=len(groups)
    numblockcol=int(np.floor(64./float(numcols)))
    numblockrow=int(np.floor(6./float(numrows)))

    tmpdecomp={}
    for blockid in range(0,numblockrow*numblockcol*numgroups):
        tmpdecomp["block_{num:0003d}".format(num=blockid)]=[]
    #hash the nodes into buckets
    for node in nodelist:
        nc=ch.nodecoords(node)
        coords=nc.get_meshcoords()
        #get group
        groupid=groups.index(nc.groupid)
        #get colid
        colid=(coords[1]*4+coords[2])
        colid=(colid-colid%numcols)/numcols
        #get rowid
        rowid=coords[0]%6
        rowid=(rowid-rowid%numrows)/numrows
        #drop the node if it is in a remainder block
        if (rowid>=numblockrow) or (colid>=numblockcol):
            continue
        blockid=rowid+numblockrow*(colid+numblockcol*groupid)
        tmpdecomp["block_{num:0003d}".format(num=blockid)].append(node)
    #now, only move the non-empty blocks over
    decomposition={}
    for item in tmpdecomp:
        if tmpdecomp[item]:
            decomposition[item]=tmpdecomp[item]
elif decompstring=="random":
    np.random.shuffle(nodelist)
    decomposition={"random": nodelist}
elif decompstring=="fuse":
    #fuse the entries back into a form: nid[XXXX,XXXX-XXXY,XXXX,...]:
    nodestring="nid["+nodelist[0].split("nid")[1]
    for node in nodelist[1:]:
        nodestring+=','+node.split("nid")[1]
    nodestring+="]"
    decomposition={'fuse':[nodestring]}
else:
    raise ValueError("Unknown mode.")

#return decomposition
for key in sorted(decomposition.keys()):
    returnstring=key+":"
    for value in decomposition[key]:
        returnstring+=value+" "
    print returnstring.replace(" ",",").strip(",")
