# SimplePeriodicWaveReader

Reads ADALM1000 using pysmu/libsmu and detects periodic waves(only supports sine waves, square waves and triangle waves)

Sample output:
```
>>> Periodic wave (7426.4 Hz) detected on Channel A!
Focus on Channel A? [y/N]: y

========================================
FOCUS ANALYSIS: CHANNEL A
Wave Type:   Square
Frequency:   7426.38 Hz
Peak-to-Peak: 3.960 V
Average:     2.459 V
Max / Min:   4.093 V / 0.133 V
========================================

Showing plot... (Close the window to continue)
```


---

# Programming for the ADALM1000 in Python

A Python library and set of tools for the Analog Devices ADALM1000 Active Learning Module.

---

This Repository builds upon @aditya-rao-iit-m's work and tries to make it easier to templatize pysmu projects and scripts. 

--- 

## Windows/Linux/Mac Install Instructions
0. Install Prefix.Dev's `pixi` as per official instructions at https://pixi.sh/latest/#installation <!-- Instructions after here will work on Windows too provided deps like python3 and git are installed-->
    - Close your terminal window and open another one after installing.
1. Ensure that `git` is already installed and are accessible from the terminal! Try running just the `git` command to see if it gives you usage instructions.  
    - If you are sure that it is not already installed, run the following command:
        ```bash
        pixi global install git
        ```  
        This will quickly set up git using the same pixi tool.
2. Prepare workspace with the command
    ```bash
    git clone https://github.com/sounddrill31/SimplePeriodicWaveReader-ADALM1000 SimplePeriodicWaveReader
    ```  
    and enter the directory
    ```bash
    cd SimplePeriodicWaveReader
    ```  
3. Run the following Command to let `pixi` setup your environment
    ```bash
    pixi install
    ```
4. Start `main.py`
    ```bash
    pixi run main
    ```
---

# Credits
## Original Program: RGB+PIO Cycle Script 
- **Author:** Aditya Rao (`23f3000019@es.study.iitm.ac.in`)
- **Program:** BS in Electronic Systems, IIT Madras
- **Date:** Friday, 5th April 2024
