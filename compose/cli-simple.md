# GUI CLI Simple

On this approach I want to combine all of the module funtion into 1 script. Instead of combining them into a single file this simple CLI will reference only to where the modules are located

Since all of the modules are done:
Odor Module
`/odor-mod-main/odor_mod_main.py`

Occupancy Module
`/occupancy-mod-main/occu_mod_main.py`

Dispenser Module
`/disp-mod-main/disp_mod_main.py`

Central Hub Module
`/central-hub-mod/cen_mod_main.py`

and the merging file output fill be the `/smart-restroom-cli-simple.py`
this time it will be a straightforward and simple monitoring and saving to the database.

## Program Flow
- The user must run the script named `/smart-restroom-cli-simple.py` and the program will start
- The program will initialize first checking all of the post message just like what each module thing to do. The order of posting and checking the module are:
  - Dispenser
  - Occupancy
  - Odor
  - Central Hub

Note: I each module have a problem initialize a specific sensor or process. Try to rerun again at least 2 times before skipping this

- Once all of the post message is done the CLI will display a status for each module like this
```
=================
Module Status
=================
Dispenser Module: Running/Error
Odor Module: Running/Error
Occupancy Module: Running/Error

```
- Then after that it will straightforward logging all of the data just like this:

```
[2025-04-29 08:59:10] Starting to log and monitor all of the data
[2025-04-29 08:59:10] Dispenser Module [2025-04-29 08:59:10] CONT1: [distance cm] [volume ml] [precentage %] | CONT2: [distance cm] [volume ml] [precentage %] | CONT3: [distance cm] [volume ml] [precentage %] | CONT4: [distance cm] [volume ml] [precentage %]
[2025-04-29 08:59:10] Odor Module ODOR [GAS1: value | GAS2: value | GAS3: value | GAS4: value | GAS5: value] TEMP [TEMP1: value | TEMP2: value | TEMP3: value | TEMP4: value]
[2025-04-29 08:59:10] Occupancy Module | Number of Visitor: | Presense: Occupied/Vacant | Visitor ID: | Total Number of Visitor: [The total number today]
```

all of them are syncronized montor every 5 seconds but still they have their own separate function of saving to the databases: remote and local
- For Dispenser module, following the difference betweent the current reading and previous reading and there is a theshold level
- For the Odor Module still follow the function that in every 10 seconds saved to the database: remote and local
- For Occupancy for every visitor who go out then saved to the remote and local

For additional context, you can analyze each of the modules
