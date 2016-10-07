from .. import os, np, pd
import pkg_resources

from ..emf_funks import (_path_manage, _check_extension, _is_number, _is_int,
                        _check_intable, _flatten, _sig_figs, _Levenshtein_group)

import subcalc_class

def load_model(*args, **kwargs):
    """Read a .REF output file and load the data into a Model object
    args:
        results_path - string, path to the output .REF file of field results or to
                the excel file exported by a Model object
        footprint_path - string, optional, path to the csv file of
                         footprint data
    kwargs:
        Bkey - string, sets 'component' of magnetic field results that the
               returned Model object accesses by default
                     - can be 'Bx', 'By', 'Bz', 'Bmax', or 'Bres'
                     - default is 'Bmax'
                     - all components are stored, none are lost
    returns
        mod - Model object containing results"""

    #check for a Bkey kwarg
    if('Bkey' in kwargs):
        Bkey = kwargs['Bkey']
    else:
        Bkey = 'Bmax'

    #check extensions
    try:
        fn = _check_extension(args[0], '.REF', '')
    except(subcalc_class.EMFError):
        fn = _check_extension(args[0], '.xlsx', """
        Can only load Models from .REF or .xlsx files""")


    if(fn[-3:] == 'REF'):

        #pull data from the REF file
        data, info = read_REF(args[0])
        #get the gridded arrays
        data = _meshgrid(data)
        #initialize Model object
        mod = subcalc_class.Model(data, info, Bkey=Bkey)
        #check for footprint file path and load if present
        if(len(args) > 1):
            mod.load_footprints(args[1])

    elif(fn[-4:] == 'xlsx'):
        #get a dict of all sheets in excel file
        dfs = pd.read_excel(args[0], sheetname=None)
        bkeys = dfs.keys()
        if('info' in bkeys):
            bkeys.remove('info')
        if('footprints' in bkeys):
            bkeys.remove('footprints')
        #slice out grid data
        x = [float(i) for i in dfs[bkeys[0]].columns]
        y = [float(i) for i in dfs[bkeys[0]].index]
        X, Y = np.meshgrid(x, y)
        data = {'X': X, 'Y': Y}
        for k in bkeys:
            data[str(k)] = dfs[k].values
        #slice out info dictionary
        info = dfs['info']
        params = info[info.columns[0]].values
        values = info[info.columns[1]].values
        info = dict(zip(params, values))
        #initialize Model object
        mod = subcalc_class.Model(data, info, Bkey=Bkey)
        #check for footprints
        if('footprints' in dfs):
            mod.load_footprints(dfs['footprints'])
        elif(len(args) > 1):
            #check for footprint file path and load if present
            mod.load_footprints(args[1])

    else:
        raise(subcalc_class.EMFError("""
        Models must be loaded from .REF file or excel files"""))

    #update model
    mod.update()
    #return
    return(mod)

def convert_REF(*args, **kwargs):
    """Convert a .REF model file to an excel file storing the same data and
    save the excel file
    args:
        REF_path - string, path to the .REF file
        footprint_path - string, optional, path to footprint csv file
    kwargs:
        path - string, path/name of output file"""

    #load and export the model
    load_model(*args, **kwargs).export(**kwargs)

def read_REF(file_path):
    """Reads a .REF output file generated by the SUBCALC program and pulls
    out information about the reference grid of the model with the Res and
    Max magnetic fields.
    args:
        file_path - string, path to saved .REF output file
    returns:
        data - dict, keys are 'x', 'y', 'Bmax', 'Bres', 'Bx', 'By', and 'Bz'
        info - dict, reference grid and other information"""

    #check the extension
    file_path = _check_extension(file_path, 'REF', """
        SubCalc results are saved to text files with .REF extensions.
        The input path:
            "%s"
        does not have the correct extension.""" % file_path)

    #allocate dictionaries
    info = {'REF_path': file_path} #dictionary storing reference grid information
    keys = ['X Coord', 'Y Coord', 'X Mag', 'Y Mag', 'Z Mag', 'Max', 'Res']
    return_keys = ['x', 'y', 'bx', 'by', 'bz', 'bmax', 'bres']
    data = dict(zip(keys, [[] for i in range(len(keys))]))

    #pull data out
    with open(file_path, 'r') as ifile:
        #store information about the grid
        for i in range(24):
            line = ifile.readline().strip()
            if(':' in line):
                idx = line.find(':')
                line = [line[:idx], line[idx+1:]]
                if(_is_number(line[1])):
                    info[line[0]] = float(line[1])
                else:
                    info[line[0]] = line[1].strip()
        #read through the rest of the data
        for line in ifile:
            for k in keys:
                if(k == line[:len(k)]):
                    L = line[line.index(':')+1:]
                    data[k].append([float(i) for i in L.split()])

    #flatten the lists in data
    for k in data:
        data[k] = np.array(_flatten(data[k]))

    #switch the keys
    data = dict(zip(return_keys, [data[k] for k in keys]))

    return(data, info)

def _meshgrid(flat_data):
    """Convert raw grid data read from a SubCalc output file
    (by subcalc_funks.read_REF) into meshed grids of X, Y coordinates
    and their corresponding B field values
    args:
        flat_data - dict, keyed by 'x','y','bx','by','bz','bmax','bres'
    returns:
        grid_data - dict with gridded arrays keyed by
                'X','Y','Bx','By','Bz','Bmax','Bres'"""

    #find the number of points in a row
    x = flat_data['x']
    y = flat_data['y']
    count = 0
    v = y[count]
    while(y[count+1] == y[count]):
        count += 1
    count += 1
    #get ncols and nrows
    L = len(x)
    ncols = count
    nrows = L/ncols
    #map old to new keys
    mapk = dict(zip(['x','y','bx','by','bz','bmax','bres'],
                    ['X','Y','Bx','By','Bz','Bmax','Bres']))
    #replace with 2D arrays
    grid_data = dict(zip([mapk[k] for k in flat_data],
                [np.reshape(flat_data[k], (nrows, ncols)) for k in flat_data]))

    return(grid_data)

def _bilinear_interp(mod, x, y):
    """Use Model results to interpolate linearly in two dimensions for an
    estimate of any x,y coordinate inside the grid.
    args:
        mod - Model object
        x - float, x coordinate to interpolate at
        y - float, y coordinate to interpolate at
    returns:
        B_interp - float, interpolated field value"""
    #first find the 4 point grid cell containing x,y
    #   (the point is assumed to lie inside the grid)
    _, xidx = _double_min(np.abs(mod.x - x))
    _, yidx = _double_min(np.abs(mod.y - y))
    #get coordinates and values
    x1, x2 = mod.x[xidx]
    y1, y2 = mod.y[yidx]
    B11 = mod.B[yidx[0], xidx[0]]
    B12 = mod.B[yidx[0], xidx[1]]
    B21 = mod.B[yidx[1], xidx[0]]
    B22 = mod.B[yidx[1], xidx[1]]
    #interpolate
    B_interp = (1.0/((x2 - x1)*(y2 - y1)))*(
        B11*(x2 - x)*(y2 - y) + B21*(x - x1)*(y2 - y)
        + B12*(x2 - x)*(y - y1) + B22*(x - x1)*(y - y1))

    return(B_interp)

def _2Dmax(G):
    """Find the indices of the maximum value in a 2 dimensional array
    args:
        G - 2D numpy array
    returns:
        m - the maximum value
        i - index of max along 0th axis
        j - index of max along 1st axis"""
    imax, jmax = 0, 0
    m = np.min(G)
    for i in range(G.shape[0]):
        for j in range(G.shape[1]):
            if(G[i,j] > m):
                m = G[i,j]
                imax = i
                jmax = j
    return(m, imax, jmax)

def _double_min(v):
    """Find the lowest two values in an array and their indices
    args:
        v - iterable
    returns:
        mins - array of minima, the first one being the smallest
        idxs - array of indices of minima"""
    if(len(v) < 2):
        raise(subcalc_class.EMFError("""
        Cannot find lowest two values in an array of length less than 2."""))
    m = max(v) #store the max for initialization
    mins = np.array([m, m], dtype=float)
    idxs = np.zeros((2,), dtype=int)
    for i in range(len(v)):
        if(v[i] < mins[0]):
            #swap first minimum to second
            mins[1] = mins[0]
            idxs[1] = idxs[0]
            #store new first minimum
            mins[0] = v[i]
            idxs[0] = i
        elif(v[i] < mins[1]):
            #store new second minimum
            mins[1] = v[i]
            idxs[1] = i

    return(mins, idxs)
