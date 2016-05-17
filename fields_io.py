"""This module/script contains a few functions to automate the management
of input and output files for the FIELDS electromagnetic fields modeling
program. It basically does two things:
    1) create input .FLD files from the excel templates
    2) convert output .DAT files to csv files with distance, maximum
       magnetic field, and maximum electric field in its columns. Plots
       of the max fields can optionally be saved as the csv files are
       generated.

Written for Python 2.7"""

import openpyxl
from os import path
from glob import glob
import numpy as np
import matplotlib.pyplot as plt
import pull_columns as pc #mmb module: P:\MBaum\Programming\Python\python_code
from is_number import is_number #mmb function: P:\MBaum\Programming\Python\python_code
from temp_csv import temp_csv #mmb module: P:\MBaum\Programming\Python\python_code

#turn off print(statements in the pull_columns module
pc.output(False)

#-------------------------------------------------------------------------------
#FUNCTIONS FOR GENERATING INPUT .FLD FILES FROM TEMPLATE WORKSHEETS

def is_int(x):
    """check if a number is an integer, will break on non-numeric entries"""
    if(int(x) == x):
        return True
    else:
        return False

#function formats entries and writes them into a .FLD file targeted by ofile
def write_entry(ofile, entry):
    """format entries and writes them into a .FLD file targeted by ofile"""
    if(is_number(entry)):
        if(is_int(entry)):
            w = '{:< d} \n'.format(int(entry))
        else:
            w = '{:< .2f} \n'.format(float(entry))
        if('.' in w):
            idx = w.index('.')
            if('0' in w[:idx]):
                idx = w.index('0')
                if(not is_number(w[idx-1])):
                    w = w[:idx] + w[idx+1:]
    else:
        w = str(entry) + '\n'
    ofile.write(w)

def create_FLDs(workbook_filename, **kwargs):
    r"""This function will create .FLD files from the sheets in a workbook,
    the path of which is passed into workbook_filename. The .FLD files are
    meant to be compatible input files for the electromagnetic field
    modeling program FIELDS. This function simply restructures the data
    in each sheet so that FIELDS can read it. To specify a destination
    directory for the files generated by create_FLDs(), use the keyword
    argument 'directory' and pass it a string with the directory path.
    Without a specified destination, the files will be created in the same
    folder as the target workbook."""

    #path management
    fn = workbook_filename
    if('directory' in kwargs.keys()):
        folder = kwargs['directory']
    else:
        folder = path.split(fn)[0]

    #get the names of all the sheets in the workbook, then delete loaded data
    wb = openpyxl.load_workbook(fn, read_only = True, data_only = True)
    sheets = wb.get_sheet_names()
    del(wb)

    #lists to keep track of names and check for duplicates or overwriting
    titles = []
    subtitles = []
    #make .FLD files for every sheet
    for sn in sheets:

        #pull out the data
        data = pc.pull_columns(fn, list(range(1,18)), 5, sheet = sn, empties = False)

        #define column index ranges for the conductors and ground lines to
        #check that their lengths are all equal
        cond_range = range(2,11)
        gnd_range = range(11,15)
        #check lengths of conductor columns
        L = len(data[cond_range[0]])
        for i in cond_range[1:]:
            if(len(data[i]) != L):
                raise(StandardError('Conductor data columns in file "%s" sheet "%s" are not the same length. Check that all necessary cells are filled in and remove extraneous entries. The imported column was:\n%s' % (fn,sn,str(data[i]))))
        #check lengths of ground wire columns
        L = len(data[gnd_range[0]])
        for i in gnd_range[1:]:
            if(len(data[i]) != L):
                raise(StandardError('Ground line data columns in file "%s" sheet "%s" are not the same length. Check that all necessary cells are filled in and remove extraneous entries. The imported columns was:\n%s' % (fn,sn,str(data[i]))))

        #perform checks on the imported data

        #store the main title field
        t = data[1][0]
        #check for accidental overwriting caused reapeating a file name
        if(t in titles):
            raise(NameError('In file "%s", sheet "%s" will cause file "%s" to be be overwritten because the contents of its "Main Title" field have already been used in a previous sheet. Use unique Main Titles for each sheet/model.' % (fn, sn, t)))
        else:
            titles.append(t)

        #store the subtitle field
        st = data[1][2]
        #check for reused subtitles, will not cause overwriting but might as
        #well be check for
        if(st in subtitles):
            print('Subtitle "%s" in sheet "%s" is used more than once.\n' % (st,sn))
        else:
            subtitles.append(t)

        #attempt to create a filename, failure being a sign that the targeted
        #worksheet is an empty template or not a template at all.
        try:
            FLD_name = sn + '.FLD'
        except TypeError as e:
            print('TypeError "%s" occured in file "%s", sheet "%s" while attempting to create a filename from cell B5. The sheet was ignored and no file was generated from it.' % (e, fn, sn))
        else:
            #write the .FLD file
            ofile = open(FLD_name, 'w')
            #miscellaneous stuff first
            for i in [0]+range(2,10):
                write_entry(ofile, data[1][i])
            #number of conductors and ground wires
            Lconds = len(data[2])
            write_entry(ofile, Lconds)
            Lgrounds = len(data[11])
            write_entry(ofile, Lgrounds)
            #write the conductor data
            for i in range(Lconds):
                for j in range(2,8):
                    write_entry(ofile, data[j][i])
                write_entry(ofile, 'ED!(I)')
                for j in [9,8,10]:
                    write_entry(ofile ,data[j][i])
            #write the ground wire data in the same format as the conductors
            for i in range(Lgrounds):
                for j in range(11,14):
                    write_entry(ofile, data[j][i])
                write_entry(ofile, 1)
                write_entry(ofile, 1)
                write_entry(ofile, data[14][i])
                write_entry(ofile, 'ED!(I)')
                write_entry(ofile, 0)
                write_entry(ofile, 0)
                write_entry(ofile, 0)
            #write the ground wire data a second time, in a different format
            for i in range(Lgrounds):
                for j in range(11,15):
                    write_entry(ofile, data[j][i])
                write_entry(ofile, 0)
                write_entry(ofile, 0)
            #close/save
            ofile.close()
            print('file generated: "%s"' % FLD_name)

def create_FLDs_crawl(dir_name, **kwargs):
    """crawl a directory and all of its subdirectories for excel workbooks
    that can be passed to create_FLDs(). The same keyword arguments that
    apply to create_FLDs() can be passed to this function."""

    #get input directory's file and subdir names
    dir_contents = glob(dir_name)
    dir_name = dir_name.rstrip('\\/*').lstrip('\\/*')

    #loop over the dir_contents, extracting if .LST is at the end and attempting
    #find subdirectories if not
    for dir_element in dir_contents:
        if(dir_element[-5:] == '.xlsx'):
            #extract from the file
            create_FLDs(dir_element, **kwargs)
        else:
            #if there's a period in the dir_element, it's not a directory
            if(not ('.' in dir_element)):
                create_FLDs_crawl(dir_element + '\\*')

#------------------------------------------------------------------------------
#FUNCTIONS FOR CONVERTING OUTPUT .DAT FILES TO CSV FILE AND PLOTTING

def DAT_to_csv(fn, **kwargs):
    """read through a DAT file created by FIELDS and convert it to a csv
    that stores the distance and maximum fields only. The data can be saved
    to a plot if the keyword argument 'plotting' is passed in with a True
    variable"""

    k = kwargs.keys()
    if('plotting' in k):
        plotting = kwargs['plotting']
    else:
        plotting = False

    #load data
    with open(fn,'r') as ifile:
        #read through the header
        for i in range(3):
            ifile.readline()
        #get the data
        d = []
        B = []
        E = []
        line = ifile.readline()
        while(line):
            if(line):
                if(line[0][0] == '%'):
                    line += ifile.readline()
            temp = [x.replace('%','') for x in line.split()]
            if(temp and all([is_number(x) for x in temp])):
                d.append(float(temp[0]))
                B.append(float(temp[4]))
                E.append(float(temp[8]))
            line = ifile.readline()
        d = np.array(d)
        B = np.array(B)
        E = np.array(E)

        #plot the data
        if(plotting):
            plot_fields(d, E, B, fn)

        #re-write the data
        h = ['Distance (ft)','Max B (mG)','Max E (kV/m)']
        temp_csv(d,B,E, filename = fn[:-4] + '_csv', header = h)

        print('file "%s" generated' % (fn[:-4] + '_csv'))

def DAT_to_csv_crawl(dir_name, **kwargs):
    """crawl a directory and all of its subdirectories for .DAT files that
    can be passed to DAT_to_csv() for output re-formatting and optional
    plotting. The same keyword arguments that apply to DAT_to_csv() can
    be passed to this function."""

    #get input directory's file and subdir names
    dir_contents = glob(dir_name)
    dir_name = dir_name.rstrip('\\/*').lstrip('\\/*')

    #loop over the dir_contents, extracting if .LST is at the end and attempting
    #find subdirectories if not
    for dir_element in dir_contents:
        if(dir_element[-4:] == '.DAT'):
            #perform a task using the filename represented by dir_element
            DAT_to_csv(dir_element, **kwargs)
        else:
            #if there's a period in the dir_element, it's not a directory
            if(not ('.' in dir_element)):
                DAT_to_csv_crawl(dir_element + '\\*')

def plot_fields(d, E, B, fn):
    """create and save a double y-axis plot of the E and B fields"""

    plt.rc('font',family='serif')

    #Emax on the left axis
    fig, ax1 = plt.subplots()
    ax1.plot(d, E, color='mediumblue',marker='.',linestyle='none')
    ax1.set_xlabel('Distance from Center of ROW (ft)')
    ax1.set_ylabel('Maximum Electric Field (kV/m)', color='mediumblue')
    for tl in ax1.get_yticklabels():
        tl.set_color('mediumblue')

    #Bmax on the right axis
    ax2 = ax1.twinx()
    ax2.plot(d, B, color='firebrick',marker='.',linestyle='none')
    ax2.set_ylabel('Maximum Magnetic Field (mG)',color='firebrick')
    for tl in ax2.get_yticklabels():
        tl.set_color('firebrick')

    plt.title('Maximum Electric and Magnetic Fields' )

    plt.savefig(fn[:-4] + '_plot')

#------------------------------------------------------------------------------
