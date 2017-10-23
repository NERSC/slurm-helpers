# source this file to get the functions into your environment

# dummy arg to add to env so bashrc can avoid unnecessarily sourcing this
_slurm_helpers_defined=1

# utility function used by other things:
dhms_to_sec () 
{
  # convert D:H:M:S to seconds
  if [[ $# -eq 1 ]]; then
    local total=0
    local -a mult=(1 60 3600 86400)
    # deal with leading -ive sign and turns day separator to :
    local a=${1:0:1}
    local b=${1:1}
    local IFS=':'
    local -a val=(${a}${b/-/:})
    unset IFS
    # leading "-" sign will now be ":"
    if [[ ${val[0]} =~ ^(-?)([0-9]+)$ ]]; then
      # deal with negatives:
      local sign=${BASH_REMATCH[1]}
      val[0]=${BASH_REMATCH[2]}
      local i=${#val[@]}
      local j=0
      (( i > 4 )) && return 1
      while (( i > 0 )); do
        let i-=1
        let total+=$(( ${val[$i]/#0}*${mult[$j]} ))
        let j+=1
      done
      #_retstr=
      printf "%s\n" "${sign}${total}"
      return 0
    fi
  fi
  return 1
}

# what was a job charged?
nersc_hours ()
{
  local mcf dhms 
  local unit=NNodes
  local qos_factor=1
  local nodes=0
  local walltime=0  # in d-hh:mm:ss
  [[ "$NERSC_HOST" == "edison" ]] && mcf=48 || mcf=80

  while [[ $# -gt 0 ]]; do
    case $1 in 
      -knl) mcf=96 ;;
      -shared) unit=NCPUS ;; 
      -prem|-premium) qos_factor=2 ;;
      -n) nodes=$2 ; shift ;;
      -t) walltime=$2 ; shift ;;
      *) jobids=$* ; break ;;
    esac
    shift
  done

  if [[ $nodes -gt 0 && "$walltime" != "0" ]]; then
    # show estimate instead
    jobids=null
  fi  

  for jobid in $jobids ; do
    if [[ $jobid == "null" ]]; then
      local usage="$walltime|$nodes|"
    else
      local usage=$(sacct -a -n -X -p -o Elapsed,$unit -j $jobid)
    fi
    usage=${usage%|}
    local dhms=${usage%%|*}
    local count=${usage##*|}
    local sec=$(dhms_to_sec $dhms)

    usage=$((count*sec*mcf*qos_factor))
    # modifications:
    if [[ "$NERSC_HOST" == "edison" ]]; then
      if [[ "$unit" == "NCPUS" ]]; then
        # charge is per core:
        usage=$((usage/24))
      fi
    else
      if [[ "$unit" == "NCPUS" ]]; then
        # charge is per core:
        usage=$((usage/32))
      elif [[ $mcf -eq 96 && $count -ge 1024 ]]; then
        echo "applying big job discount" >&2
        usage=$((usage*4/5))
      fi
    fi

    # at this point we have NERSC-seconds, convert to NERSC-hours:
    usage=$((usage/3600))
    echo "$usage"
  done
}

# not slurm related, but when we usgrsu to a user account, it's nice to get the X forwarding stuff displayed upfront
# (paste the string this prints into the terminal as the user)
user () 
{ 
  [[ -z $DISPLAY ]] || echo "export DISPLAY=$DISPLAY ; xauth add `xauth list $DISPLAY`" ; usgrsu $* 
}

# show what jobs have run on a given node or list of nodes, during the last day
nodehistory () 
{ 
  sacct --node=$1 --format=start,end,job,jobname,user,account,ncpus,nodelist -X  
}

# handy function to get the more useful info about jobs:
jobsummary () 
{ 
  local opts='' 
  local f='JobID%-20,User,Submit,Start,End,State,ExitCode,DerivedExitCode,Elapsed,Timelimit,NNodes,NCPUS,NTasks' ; 
  local s1="1s/ +NodeList/ Nodelist/; 2s/(^.{$COLUMNS}).*/\1/"
  local s2="; s/(^.{$COLUMNS}).*/\1/"
  local compact="-X"  # normally show -X only, unless -F (for "full") passed in
  show=:  # null command
  while [[ -n "$1" ]] ; do 
    case $1 in 
      -v) show=echo ; s2="; s/ *$//" ; shift ;;     # long display
      -o) f+=",$2" ; shift 2 ;;                     # add fields like -o option of sacct (need to leave space after -o)
      -j) compact="" ; opts+=" $1 $2" ; shift 2 ;;  # job id
      -F) compact="" ; shift ;;                     # opposite of saact -X
       *) opts+=" $1" ;  shift ;;                   # pass options through to sacct (eg -S...)
    esac
 done
 f+=',nodelist%-2500' 
 $show sacct -a $compact -o $f $opts ; sacct -a $compact -o $f $opts | sed -r "$s1 $s2" | less -FX 
}

# this cancels all my jobs:
function sclear () 
{ 
  local args="$*" 
  [[ -z "$args" ]] && args=$(squeue -u $USER -t R,PD -o %A -h | tr '\n' ' ') 
  echo "cancelling jobs:" 
  squeue -j ${args// /,}
  ${SLURM_ROOT:-/usr}/bin/scancel $args 
}

# list info about qos and partitions:
qos () { sacctmgr show -p qos | cut -d'|' -f 1,2,9,12,15,18,19,20,21 | column -s '|' -t ; }
partitions () { sinfo -O "partition,available:6,time:.12,nodes:.6" ; }

res_compact_nodelist() 
{
    resname=$1
    scontrol --oneliner show res=$resname | cut -d ' ' -f 5 | cut -d '=' -f 2
}

res_nodelist() 
{
    resname=$1
    compact_list=$(res_compact_nodelist "$resname")
    scontrol show hostname $compact_list
}

res_get_modes() 
{
    resname=$1
    compact_list=$(res_compact_nodelist "$resname")
    sinfo --format="%15b %8D %9A %N" --nodes=$compact_list
}

res_set_mode() 
{
    resname=$1
    mode=$2
    echo setting $mode for $resname
    nodelist=$(res_nodelist "$resname")
    for node in $nodelist; do
        sbatch -C $mode -p regular --reservation=$resname --nodelist=$node \
            --output="modeset-%j.out" \
            --wrap="hostname"
    done
}
