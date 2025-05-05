# Merging Modules
Since all of the modules are done:
Odor Module
`/odor-mod-main/odor-mod-main.py`

Occupancy Module
`/occupancy-mod-main/occu-mod-main.py`

Dispenser Module
`/disp-mod-main/disp-mod-main.py`

Central Hub Module
`/central-hub-mod/cen-mod-main.py`

all are in the same project named `/prototype-thesis`
I want this kind of approach, instead of merging them as one and make a lengthy line which is make more not maintainable when dubgging instead importing them from the main python script `/smart-restroom-cli.py` and call or import from the external scripts which I have mentioned on the above.

The GUI CLI still remains but the function and the method will implement this new approach that I have presented to you.

```
import odor_mod from "/odor-mod-main/odor-mod-main.py"
import occu_mod from "/odor-mod-main/odor-mod-main.py"
import disp_mod from "/disp-mod-main/disp-mod-main.py"
import cent_mod from "/central-hub-mod/cen-mod-main.py"

```

I want like that that it will create a function then it will call each of the modulars fucntion from the external