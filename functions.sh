# source this file to get the functions into your environment

# dummy arg to add to env so bashrc can avoid unnecessarily sourcing this
_slurm_helpers_defined=1

alias scn=scontrol

admincomment () { 
  local j=$2 ; shift; shift;
  echo sacct $* -X -n -P -o admincomment $* -j $j 
  sacct $* -X -n -P -o admincomment $* -j $j | jq ; }

# utility function used by other things:
# (this is here mostly in suport of nersc_hours)
dhms_to_sec () 
{
  local usage="$0 D:H:M:S"$'\n'
  usage+='print number of seconds corresponding to a timespan'$'\n'
  usage+='copes with leading negative sign'$'\n'
  usage+='accepted formats are:'$'\n'
  usage+='  [-][[[D:]H:]M:]S'$'\n'
  usage+='  [-][[[D-]H:]M:]S'$'\n'
  usage+='Examples:'$'\n'
  usage+='  1-12:00:00     1 day 12 hours'$'\n'
  usage+='  2:00:01:00     2 days and 1 minute'$'\n'
  usage+='  -30:00         negative half an hour'$'\n'
  if [[ $# -ne 1 || $1 =~ ^-h ]] ; then
    echo "$usage"
    return 1
  else
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
  echo "$usage"
  return 1
}

# what was a job charged?
nersc_hours ()
{
  local usage="calculate NERSC-hours for a completed job, or set of jobs,"$'\n'
  usage+="or a walltime and nodecount"$'\n'
  usage+="sets machine charge factor based on current NERSC_HOST ($NERSC_HOST)"$'\n'
  usage+="Usage: $0 [-knl] [-prem] [-shared] <jobid1> <jobid2> ..."$'\n'
  usage+="Usage: $0 [-knl] [-prem] -n <nodecount> -t <walltime-in-d-hh:mm:ss>"$'\n'
  local mcf dhms 
  local unit=NNodes
  local qos_factor=1
  local nodes=0
  local walltime=0  # in d-hh:mm:ss
  #[[ "$NERSC_HOST" == "edison" ]] && mcf=48 || mcf=80
  [[ "$NERSC_HOST" == "edison" ]] && mcf=64 || mcf=140

  if [[ $# -eq 0 ]]; then
    echo "$usage"
    return 1
  fi
  local -a jobids
  while [[ $# -gt 0 ]]; do
    case $1 in 
      -h*) echo "$usage" ; return 1 ;;
      -m) mcf=$2 ; shift ;;
      #-knl) mcf=96 ;;
      -knl) mcf=80 ;;
      -shared) unit=NCPUS ;; 
      -prem|-premium) qos_factor=2 ;;
      -n) nodes=$2 ; shift ;;
      -t) walltime=$2 ; shift ;;
#      *) jobids=($*) ; break ;;
      *) jobids=( $(tr ',' ' ' <<< "$*") ) ; break ;;
    esac
    shift
  done

  if [[ $nodes -gt 0 && "$walltime" != "0" ]]; then
    # show estimate instead
    jobids=( null )
  fi  

  local total=0
  for jobid in ${jobids[@]} ; do
    if [[ $jobid == "null" ]]; then
      local usage="$walltime|$nodes|"
    else
      local usage=$(sacct --noconvert -a -n -X -p -o Elapsed,$unit -j $jobid)
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
      #elif [[ $mcf -eq 96 && $count -ge 1024 ]]; then
      elif [[ $mcf -eq 90 && $count -ge 1024 ]]; then
        echo "applying big job discount" >&2
        usage=$((usage*1/2))
      fi
    fi
    let total+=$usage

    # at this point we have NERSC-seconds, convert to NERSC-hours:
    usage=$((usage/3600))
    echo "job $jobid: $usage nersc-hours"
  done
  if [[ ${#jobids[@]} -gt 1 ]]; then
    total=$((total/3600))
    echo "total: $total nersc-hours"
  fi
}

# not slurm related, but when we usgrsu to a user account, it's nice to get the X forwarding stuff displayed upfront
# (paste the string this prints into the terminal as the user)
user () 
{ 
  [[ -z $DISPLAY ]] || echo "export DISPLAY=$DISPLAY ; xauth add `xauth list $DISPLAY`" ; echo "alias vi='vi -u NONE'"; usgrsu $* 
}

# show what jobs have run on a given node or list of nodes, during the last day
nodehistory () 
{ 
  #sacct --node=$1 --format=start,end,job,jobname,user,account,ncpus,nodelist,exitcode -X  
  node=$1 ; shift
  SLURM_TIME_FORMAT='%s' sacct --node=$node $* --format=start,end,job,jobname,user,account,ncpus,nodelist,exitcode -X | awk 'NR<=2 {print "           " $0 ;} NR>2 { key=$1 ; $1=strftime("%Y-%m-%d-%H:%M:%S", $1); $2=strftime("%Y-%m-%d-%H:%M:%S", $2); print key "    " $0 | "column -t | sort -sn -k1"}'
}

jobsummary () 
{ 
  # NOTE: if job state 'RV' is specified, you get pending jobs as well as completed ones, 
  # even if you didn't request them
  local opts='-D' 
  local f='JobID%-20,User,Submit,Start,End,State,ExitCode,DerivedExitCode,Elapsed,Timelimit,NNodes,NCPUS,NTasks' ; 
  local s1="1s/ +NodeList/ Nodelist/; 2s/(^.{$COLUMNS}).*/\1/"
  local s2="; s/(^.{$COLUMNS}).*/\1/"
  local compact="-X"  # normally show -X only, unless -F (for "full") passed in
  local since=$(date +%D --date='last week')
  show=:  # null command
  while [[ -n "$1" ]] ; do 
    case $1 in 
      -v) show=echo ; s2="; s/ *$//" ; shift ;;     # long display
      -o) f+=",$2" ; shift 2 ;;                     # add fields like -o option of sacct (need to leave space after -o)
      -j) compact="" ; opts+=" $1 $2" ; shift 2 ;;  # job id
      -F) compact="" ; shift ;;                     # opposite of saact -X
      -S) since="$2" ; shift 2 ;;
       *) opts+=" $1" ;  shift ;;                   # pass options through to sacct (eg -S...)
    esac
 done
 f+=',nodelist%-15000' 
 #$show sacct -a $compact -S $since -o $f $opts ; sacct -a $compact -S $since -o $f $opts | sed -r "$s1 $s2" | less -FX 
 #$show sacct -a $compact -S $since -o $f $opts ; sacct -a $compact -o $f $opts | sed -r "$s1 $s2" | less -FX 
 cmdline="sacct -a $compact -S $since -o $f $opts"
 $show $cmdline
# $cmdline | sed -r "$s1 $s2" | less -FX
 $cmdline | sed -r "$s1 $s2" | sed 's/  *$//' | $PAGER
}

# this cancels all my jobs:
function sclear () 
{ 
  ${SLURM_ROOT:-/usr}/bin/scancel -u $USER
}

# list info about qos and partitions:
qos () { sacctmgr show -p qos $* | cut -d'|' -f 1,2,9,12,15,18,19,20,21 | column -s '|' -t ; }
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
    # if the reservation is not yet active, don't specify it:
    scontrol show res $resname | grep -q 'State=INACTIVE' && resname=""
    for node in $nodelist; do
        sbatch -C $mode -p regular "${resname:+--reservation=$resname}" \
            --nodelist=$node \
            --output="modeset-%j.out" \
            --wrap="hostname"
    done
}

function body ()
{
  # run a stream command, but exempt the first line (or -n lines) from it - 
  # eg for if I want to print the header line then grep for certain text in
  # the remaining lines:
  local nh=1;
  if [[ "$1" =~ -[0-9] ]]; then
      nh=${1#-};
      shift;
  fi;
  cmd="$*";
  awk 'NR <= '$nh'; NR > '$nh' {print $0 | "'"$cmd"'"}'
}

#function pager ()
#{
#    in=$1 ; h=$(head -1 $1)
#    if [[ -z $in ]] ; then
#      h=$(head -1 /dev/stdin)
#    fi
#    echo "$h" 
#    #header=$(head -1 /dev/stdin)
#    #less -PM"$h" -FX $in
#}

## short display:  Q_pos  Jobid  State  Partition User Name  Nodes TimeLeft  Priority  Reason  (need to capture priority and state for sorting too)
## long display:   Q_pos  Jobid  State  Partition QOS User  Account  Name  Nodes CPUs TimeLimit  TimeLeft  Submittime Starttime Priority  Reason
#function myq () 
#{
#  local grepargs=""
#  local user=$USER
#  local addfields=""
#  local timef='function dhms(ss) { if (ss<0) { sign="-"; s=-ss } else { sign="" ; s=ss }; d=int(s/86400); s=s-(d*86400) ; h=int(s/3600) ;s=s-(3600*h) ; m=int(s/60) ;s=s-(m*60) ; return sprintf("%s%dd-%02d:%02d:%02d",sign,d,h,m,s);} BEGIN { t=systime() }'
#  local longfmt=0
#  if [[ $COLUMNS -ge 200 ]]; then longfmt=1; fi   # I kinda like the long display if theres room for it
#  while [[ $# -gt 0 ]]; do
#    case $1 in 
#      -a) user="" ; shift ;;
#      -u) user=$2 ; shift 2 ;;
#      -l) longfmt=1 ; shift ;;
#      -s) longfmt=0 ; shift ;;
#      -o) addfields="$2" ; shift 2 ;;
#      *)  break ;;
#    esac 
#  done
#  if (( $longfmt )) ; then
#    local fields='%.18i %.4t %8q %10P %8u %8a %20j %.6D %.6C %.10l %.10L %.20V %.20S %.10Q %.20r %.30E'
#    local pf=14
#    local usetimef="qt=dhms(t-\$12); out=gensub (/[[:blank:]]+[^[:blank:]]+/, sprintf(\"%21s\",qt),12); if (\$13~/[0-9]+/) {st=dhms(\$13-t) } else if (\$NF~/Resources/ && t-\$12>180) {st=\">4d\"} else {st=\$13}; out=gensub (/[[:blank:]]+[^[:blank:]]+/, sprintf(\"%21s\",st), 13, out);"
#  else
#    local fields='%.18i %.4t %8q %8u %20j %.6D %.10L %.10Q %.12r'
#    local pf=8  # priority field
#    local usetimef='out=$0;'
#  fi
#  fields+=" $addfields"
#  grepargs="$user $*" 
#  local awkscr="$timef NR==1 { gsub(/SUBMIT_TIME/, \"TIME_QUEUED\") ; print } NR>1 { $usetimef print out | \"sort -rsn -k$pf\" }"
#  local wholeq=$(SLURM_TIME_FORMAT='%s' squeue -r -t PD,R,CF,CG -o "$fields" | awk "$awkscr" | awk 'BEGIN { spos=0 ; rpos=0 ; notready="" } NR == 1 { print "0    Q_pos " $0 ; next } $2~/^[RC]/ { print "1        0 " $0; next } $NF~/Priority|Resources|ReqNodeNotAvail/ { line=$0 ; if ($3=="shared") { spos+=1 ; pos=spos } else {rpos+=1 ; pos=rpos } ; printf "2 %8d %s\n",pos,$0 ; next } { printf "3 %8s %s\n", "NotReady", $0 } ')
#  # less -PM"$h" q h=`head -1 q`
#  header=$(head -1 <<< "$wholeq" | cut -c-${COLUMNS})
##  header="0    Q_pos $header"
#  grepargs=${grepargs## }
#  if [[ ${#grepargs} -gt 0 ]]; then 
#    local search=""
#    for t in $grepargs ; do 
#      search+=" -e $t" 
#    done
#    body grep $search <<< "$wholeq" | body sort -sn -k1,2 | cut -c2- | less -PM"$header" -FX 
#    #body grep $search <<< "$wholeq" | body sort -sn -k1,2 | cut -c2- | pager 
#  else 
#    body sort -sn -k1,2 <<< "$wholeq" | cut -c2- | less -PM"$header" -FX 
#    #body sort -sn -k1,2 <<< "$wholeq" | cut -c2- | pager
#  fi 
#}
# short display:  Q_pos  Jobid  State  Partition User Name  Nodes TimeLeft  Priority  Reason  (need to capture priority and state for sorting too)
# long display:   Q_pos  Jobid  State  Partition QOS User  Account  Name  Nodes CPUs TimeLimit  TimeLeft  Submittime Starttime Priority  Reason
function myq () 
{
  local grepargs=""
  local user=$USER
  local addfields=""
  #local fields='%.18i %.4t %10P %8u %20j %.6D %.10L %.10Q %.12r'
  #local pf=8  # priority field
  local timef='function dhms(ss) { if (ss<0) { sign="-"; s=-ss } else { sign="" ; s=ss }; d=int(s/86400); s=s-(d*86400) ; h=int(s/3600) ;s=s-(3600*h) ; m=int(s/60) ;s=s-(m*60) ; return sprintf("%s%dd-%02d:%02d:%02d",sign,d,h,m,s);} BEGIN { t=systime() }'
  local longfmt=0
  if [[ $COLUMNS -ge 200 ]]; then longfmt=1; fi   # I kinda like the long display if theres room for it
  #local usetimef='out=$0;'
  while [[ $# -gt 0 ]]; do
    case $1 in 
      -a) user="" ; shift ;;
      -u) user=$2 ; shift 2 ;;
      -l) longfmt=1 ; shift ;;
      -s) longfmt=0 ; shift ;;
      -o) addfields="$2" ; shift 2 ;;
#      -l) fields='%.18i %.4t %10P %8q %8u %8a %20j %.6D %.6C %.10l %.10L %.20V %.20S %.10Q %.12r'; pf=14; shift ; usetimef="qt=dhms(t-\$12); out=gensub (/[[:blank:]]+[^[:blank:]]+/, sprintf(\"%21s\",qt),12); if (\$13~/[0-9]+/) {st=dhms(\$13-t) } else if (\$NF~/Resources/) {st=\">4d\"} else {st=\$13}; out=gensub (/[[:blank:]]+[^[:blank:]]+/, sprintf(\"%21s\",st), 13, out);" ;;
      *)  break ;;
    esac 
  done
  if (( $longfmt )) ; then
    local fields='%.18i %.4t %8q %10P %8u %8a %20j %.6D %.6C %.10l %.10L %.20V %.20S %.10Q %.20r %.30E'
    local pf=14
    local rf=15 # reason field
    local usetimef="qt=dhms(t-\$12); out=gensub (/[[:blank:]]+[^[:blank:]]+/, sprintf(\"%21s\",qt),12); if (\$13~/[0-9]+/) {st=dhms(\$13-t) } else if (\$NF~/Resources/ && t-\$12>180) {st=\">4d\"} else {st=\$13}; out=gensub (/[[:blank:]]+[^[:blank:]]+/, sprintf(\"%21s\",st), 13, out);"
  else
    local fields='%.18i %.4t %8q %8u %20j %.6D %.10L %.10Q %.12r'
    local pf=8  # priority field
    local rf=9 # reason field
    local usetimef='out=$0;'
  fi
  fields+=" $addfields"
  grepargs="$user $*" 
  local awkscr="$timef NR==1 { gsub(/SUBMIT_TIME/, \"TIME_QUEUED\") ; print } NR>1 { $usetimef print out | \"sort -rsn -k$pf\" }"
  #local wholeq=$(SLURM_TIME_FORMAT='%s' squeue -r -t PD,R -o "$fields" | awk "$awkscr" | awk 'BEGIN { spos=0 ; rpos=0 ; notready="" } NR == 1 { print "0    Q_pos " $0 ; next } $2=="R" { print "1        0 " $0; next } $NF~/Priority|Resources/ { line=$0 ; if ($3=="shared") { spos+=1 ; pos=spos } else {rpos+=1 ; pos=rpos } ; printf "2 %8d %s\n",pos,$0 ; next } { printf "3 %8s %s\n", "NotReady", $0 } ' | body sort -sn -k1,2 | cut -c2-)
  local wholeq=$(SLURM_TIME_FORMAT='%s' squeue -r -t PD,R,CF,CG -o "$fields" | awk "$awkscr" | awk 'BEGIN { spos=0 ; rpos=0 ; notready="" } NR == 1 { print "0    Q_pos " $0 ; next } $2~/^[RC]/ { print "1        0 " $0; next } $'$rf'~/Priority|Resources|ReqNodeNotAvail/ { line=$0 ; if ($3=="shared") { spos+=1 ; pos=spos } else {rpos+=1 ; pos=rpos } ; printf "2 %8d %s\n",pos,$0 ; next } { printf "3 %8s %s\n", "NotReady", $0 } ')

  grepargs=${grepargs## }
  if [[ ${#grepargs} -gt 0 ]]; then 
    local search=""
    for t in $grepargs ; do 
      search+=" -e $t" 
    done
    body grep $search <<< "$wholeq" | body sort -sn -k1,2 | cut -c2- | less -FX
  else 
    body sort -sn -k1,2 <<< "$wholeq" | cut -c2- | less -FX 
  fi 
}
function showq () { myq -l -a $* ; }

#function showq () { myq -l -a $* ; }
