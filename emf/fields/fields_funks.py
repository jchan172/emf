import os
import copy
import itertools
import numpy as np
import pandas as pd

from ..emf_funks import (_path_manage, _check_extension, _is_number,
                            _check_intable, _flatten)

import fields_class
import fields_calcs
import fields_plots

def load_template(file_path, **kwargs):
    """Import conductor data from an excel template, loading each conductor
    into a Conductor object, each Conductor into a CrossSection object, and
    each CrossSection object into a SectionBook object. The SectionBook
    object is returned.
    args:
        template_path - string, path to cross section template excel
                        workbook
    kwargs:
        sheets - list of strings, a list of sheet names to load, default is
                 all sheets"""
    #import the cross sections as a dictionary of pandas DataFrames, also
    #getting a list of the ordered sheets
    file_path = _check_extension(file_path, 'xlsx', """
        Templates must be excel workbooks. The input target path
            "%s"
        is not recognized as an excel file""" % file_path)
    xl = pd.ExcelFile(file_path)
    sheets = xl.sheet_names
    frames = xl.parse(sheetname = None, skiprows = [0,1,2,3], parse_cols = 16,
                    header = None)
    #remove necessary sheets if the 'sheets' keyword is passed in
    if('sheets' in kwargs):
        include = kwargs['sheets']
        sheets = [sh for sh in sheets if sh in include]
    #create a SectionBook object to store the CrossSection objects
    basename = os.path.basename(file_path)
    if('.' in basename):
        name = basename[:basename.index('.')]
    else:
        name = basename
    sb = fields_class.SectionBook(name)
    #convert the dataframes into a list of CrossSection objects
    titles = []
    for k in sheets:
        #load miscellaneous information applicable to the whole CrossSection
        df = frames[k]
        xc = fields_class.CrossSection(k)
        misc = df[1]
        xc.title = misc[0]
        xc.tag = misc[1]
        #check for duplicate title inputs
        if(xc.title in titles):
            raise(fields_class.EMFError("""
            Cross-sections should have unique Main Title entries.
            Main Title: "%s"
            in sheet: "%s"
            is used by at least one other sheet.""" % (xc.title, k)))
        else:
            titles.append(xc.title)
        xc.subtitle = misc[2]
        xc.soil_resistivity = misc[4]
        xc.max_dist = misc[5]
        xc.step = misc[6]
        xc.sample_height = misc[7]
        xc.lROW = misc[8]
        xc.rROW = misc[9]
        #load hot conductors
        tags, x, y = [], [], []
        for i in range(df[3].dropna().shape[0]):
            cond = fields_class.Conductor()
            cond.tag = df[2].iat[i]
            #check for conductors with identical tags (names/labels)
            if(cond.tag in tags):
                raise(fields_class.EMFError("""
                Conductors in a Cross Section must have unique tags.
                The conductor tag "%s" in sheet:
                    "%s"
                is used at least twice."""
                % (cond.tag, k)))
            else:
                tags.append(cond.tag)
            cond.freq = misc[2]
            cond.x = df[3].iat[i]
            cond.y = df[4].iat[i]
            #check for conductors with identical x,y coordinates
            if(cond.x in x):
                idx = x.index(cond.x)
                if(cond.y == y[idx]):
                    raise(fields_class.EMFError("""
                Conductors cannot have identical x,y coordinates. Conductor
                "%s" is in the exact same place as conductor "%s"."""
                % (cond.tag, tags[idx])))
            else:
                x.append(cond.x)
                y.append(cond.y)
            cond.subconds = df[5].iat[i]
            cond.d_cond = df[6].iat[i]
            cond.d_bund = df[7].iat[i]
            cond.V = df[8].iat[i]
            cond.I = df[9].iat[i]
            cond.phase = df[10].iat[i]
            xc.hot.append(cond)
        #load grounded conductors
        tags, x, y = [], [], []
        for i in range(df[12].dropna().shape[0]):
            cond = fields_class.Conductor()
            cond.tag = df[11].iat[i]
            #check for conductors with identical tags (names/labels)
            if(cond.tag in tags):
                raise(fields_class.EMFError("""
                Conductors in a Cross Section must have unique tags.
                The conductor tag "%s" in sheet:
                    "%s"
                is used at least twice."""
                % (cond.tag, k)))
            else:
                tags.append(cond.tag)
            cond.freq = misc[2]
            cond.x = df[12].iat[i]
            cond.y = df[13].iat[i]
            #check for conductors with identical x,y coordinates
            if(cond.x in x):
                idx = x.index(cond.x)
                if(cond.y == y[idx]):
                    raise(fields_class.EMFError("""
                Conductors cannot have identical x,y coordinates. Conductor
                "%s" is in the exact same place as conductor "%s"."""
                % (cond.tag, tags[idx])))
            else:
                x.append(cond.x)
                y.append(cond.y)
            cond.subconds = 1.
            cond.d_cond = df[14].iat[i]
            cond.d_bund = df[14].iat[i]
            cond.V = 0.
            cond.I = 0.
            cond.phase = 0.
            xc.gnd.append(cond)
        #add the CrossSection object to the SectionBook
        sb.add_section(xc)
    #update the SectionBook, which initiates fields calculations and
    #population of lots of other variables in the CrossSection and SectionBook
    #objects
    sb.update()
    #return the SectionBook object
    return(sb)

def optimize_phasing(xc, circuits, **kwargs):
    """Permute the phasing of non-grounded conductors and find the
    arrangement that results in the lowest fields at the left and right
    edge of the ROW. The number of hot conductors must be a multiple of
    three. The phases of consecutive groups of three conductors are
    swapped around, assuming that those groups represent a single
    three-phase transfer circuit.
    args:
        xc - target CrossSection object
        circuits - list of lists of ints, or 'all'. If a list of lists,
                   each sublist contains the integer indices of the
                   conductors that belong to a circuit, indexed from zero.
                   If 'all', circuits are assumed to be consecutive groups
                   of three conductors.
    kwargs:
        save - bool, toggle saving of the results DataFrame to an excel book
        path - string, location/filename for saved results workbook, forces
               saving even if no 'save' keyword is used.
    returns:
        res - pandas DataFrame listing conductor phasings that optimize
              electric and magnetic fields at both ROW edges.
        opt - new SectionBook object containing the permuted phasings that
              optimize the E and B fields at the left and right ROW edges."""

    if(circuits == 'all'):
        #number of hot wires
        N = len(xc.hot)
        #check the number of hot lines
        if(N % 3 != 0):
            raise(fields_class.EMFError("""
            The number of hot (not grounded) conductors must be a multiple
            of three for phase optimization with 'all' circuits. Circuits are
            assumed to be three-phase and conductors comprising each circuit
            are assumed to be consecutive groups of three, in the order that
            they appear in the template. The number of hot conductors is not a
            multiple of three in the CrossSection named: "%s" """ % xc.name))
        #number of circuits, groups of 3 hot conductors
        G = int(N/3)
        #circuits, consecutive groups of three conductors
        circuits = [range(i*3,i*3 + 3) for i in range(G)]
    else:
        #check that all conductor indices are integers
        for circ in range(len(circuits)):
            for idx in circ:
                if(type(idx) is not int):
                    raise(fields_class.EMFError("""
                    Conductor indices in circuits must be integers."""))
    #all permutations of the phases of each circuit
    perm = []
    for c in circuits:
        perm.append(list(itertools.permutations(c)))
    #all possible arrangements of line phasings, 6 permutations for each circuit
    #so 6^(N/3) total line arrangements. Leave P as a generator to avoid storing
    #a huge, factorial sized array of indices
    P = itertools.product(*perm)
    #variables to find the minima with respect to each field and ROW edge
    B_left_min, B_left_arr, B_right_min, B_right_arr = np.inf, [], np.inf, []
    E_left_min, E_left_arr, E_right_min, E_right_arr = np.inf, [], np.inf, []
    #make sure the necessary CrossSection variables are set
    xc.update_arrays()
    #get coordinates of the ROW edges
    x_ROW = np.array([xc.x_sample[xc.lROWi], xc.x_sample[xc.rROWi]])
    y_ROW = np.array([xc.y_sample[xc.lROWi], xc.y_sample[xc.rROWi]])
    #array for swapping phases, zeros in the grounded slots
    phasing = xc.phase.copy()
    #store a flattened version of the conductor indices for swapping
    conds = np.array([item for sublist in circuits for item in sublist],
                dtype = int)
    #loop through all possible arrangements in P
    for arr in P:
        #calculate fields at ROW edges with the new arrangement
        Bmax,Emax,new_arr = _phasing_test(xc, x_ROW, y_ROW, conds, phasing, arr)
        #test for minima
        if(Bmax[0] < B_left_min):
            B_left_min, B_left_arr = Bmax[0], new_arr
        if(Bmax[1] < B_right_min):
            B_right_min, B_right_arr = Bmax[1], new_arr
        if(Emax[0] < E_left_min):
            E_left_min, E_left_arr = Emax[0], new_arr
        if(Emax[1] < E_right_min):
            E_right_min, E_right_arr = Emax[1], new_arr
    #return results in a DataFrame
    results = pd.DataFrame(data = {
        'Optimal Phasing - Bmax Left ROW Edge' : xc.phase[B_left_arr],
        'Optimal Phasing - Bmax Right ROW Edge' : xc.phase[B_right_arr],
        'Optimal Phasing - Emax Left ROW Edge' : xc.phase[E_left_arr],
        'Optimal Phasing - Emax Right ROW Edge' : xc.phase[E_right_arr]},
        index = [xc.hot[i].tag for i in conds])
    #compile a new sectionbook with the optimal phasings
    opt = fields_class.SectionBook('%s-optimal_phasing' % xc.title)
    names = ['Optimized_for_Bmax_left','Optimized_for_Bmax_right',
            'Optimized_for_Emax_left','Optimized_for_Emax_right']
    titles = ['Bmax_l','Bmax_r','Emax_l','Emax_r']
    tags = ['Optimized for Magnetic Field']*2+['Optimized for Electric Field']*2
    subtitles = results.columns
    for n,ti,s,ta in zip(names, titles, subtitles, tags):
        #copy the input XC
        new_xc = copy.deepcopy(xc)
        #change the identification fields
        new_xc.name, new_xc.title, new_xc.subtitle, new_xc.tag = n, ti, s, ta
        #swap the conductor phasings
        for c in new_xc.hot:
            t = c.tag
            if(t in results.index):
                c.phase = results.at[t, s]
        #store new_xc in the SectionBook
        opt.add_section(new_xc)
    #update everything in the SectionBook
    opt.update()
    #deal with saving
    if('path' in kwargs):
        kwargs['save'] = True
    if('save' in kwargs):
        if(kwargs['save']):
            fn = _path_manage(xc.name + '_phase_optimization', 'xlsx', **kwargs)
            xl = pd.ExcelWriter(fn, engine = 'xlsxwriter')
            results.to_excel(xl, index_label = 'Conductor Tag',
                sheet_name = 'phase_assignments')
            opt.ROW_edge_export(xl = xl)
            for xc in opt:
                xc.fields.to_excel(xl, sheet_name = xc.name)
            xl.save()
            print('Phase optimization results written to "%s"' % fn)

    return(results, opt)

def _phasing_test(xc, x_ROW, y_ROW, conds, phasing, arr):
    """Calculate fields at the ROW edges for a given phasing arrangement,
    called by optimize_phasing()
    args:
        xc - CrossSection object with phases to test
        x_ROW - numpy array of the ROW edge x coordinates, to avoid repeated
                creation of this array for fields_calcs to work on
        y_ROW - numpy array of the ROW edge y coordinates, to avoid repeated
                creation of this array for fields_calcs to work on
        conds - array of ints, indices of conductors in xc.hot under
                consideration
        phasing - numpy array, a copy of xc.phase to mess with
        arr - numpy array, permuted phases for the conductors indexed by
              conds, list of lists that will be flattened
    returns:
        Bmax - array of two B field values, the 0th being the field at the
               left ROW edge, 1st is at right ROW edge
        Emax - array of two E field values, the 0th being the field at the
               left ROW edge, 1st is at right ROW edge
        new_arr - flattened version of arr in case it needs to be stored"""
    #flatten the new arrangement
    new_arr = _flatten(arr)
    #swap phases according to the new phasing arrangement
    phasing[conds] = xc.phase[new_arr]
    #calculate fields with index swapped phases
    Ex, Ey = fields_calcs.E_field(xc.x, xc.y, xc.subconds, xc.d_cond,
                                xc.d_bund, xc.V, phasing, x_ROW, y_ROW)
    Ex, Ey, Eprod, Emax = fields_calcs.phasors_to_magnitudes(Ex, Ey)
    Bx, By = fields_calcs.B_field(xc.x, xc.y, xc.I, phasing, x_ROW, y_ROW)
    Bx, By, Bprod, Bmax = fields_calcs.phasors_to_magnitudes(Bx, By)
    #return results
    return(Bmax, Emax, new_arr)

def target_fields(xc, hot, gnd, B_l, B_r, E_l, E_r, **kwargs):
    """Increase conductor y coordinates until fields at ROW edges are below
    thresholds. All selected conductors are adjusted by the same amount.
    If any of the thresholds are empty or false, None is returned for their
    adjustment result.
    args:
        xc - CrossSection object to perform adjustments on
        hot - indices of hot conductors in self.hot to raise, accepts 'all'
        gnd - indices of ground conductors in self.gnd to raise,
              accepts 'all'
        B_l - magnetic field threshold at left ROW edge*
        B_r - magnetic field threshold at right ROW edge*
        E_l - electric field threshold at left ROW edge*
        E_r - electric field threshold at right ROW edge*

            *an implicitly False input will ignore that field-edge
             combination, return None in the return variable 'h', and
             cause the returned SectionBook to omit that field-edge combo.

    kwargs:
        max_iter - maximum number of _bisection iterations allowed
                   default is 1e3
        rel_err - tolerance threshold for relative error (e.g. 0.01 is 1 %)
                  default is 1e-6.
        hhigh - upper limit of the height adjustment, default is 1.0e6
        save - toggle saving of the results DataFrame to an excel book
        path - location/filename for saved results workbook, forces saving
               even if no 'save' keyword is used.
    returns:
        h - height adjustments necessary for E and B fields at left and
            right ROW edges. The ordering is:
                    (B_left, B_right, E_left, E_right)
        adj - a new SectionBook object with the adjusted conductor heights
             for each scenario in a CrossSection"""
    #convert 'all' inputs to numeric indices
    if(hot == 'all'):
        hot = list(range(len(xc.hot)))
    if(gnd == 'all'):
        gnd = list(range(len(xc.gnd)))
    #maximum number of iterations and relative error tolerance
    if('max_iter' in kwargs):
        max_iter = kwargs['max_iter']
    else:
        max_iter = 1e3
    if('rel_err' in kwargs):
        rel_err = kwargs['rel_err']
    else:
        rel_err = 1.0e-6
    if('hhigh' in kwargs):
        hhigh = kwargs['hhigh']
    else:
        hhigh = 1.0e6
    hlow = 0.0
    #flattened indices
    conds = np.array(list(hot) + [len(xc.hot) + i for i in gnd])
    #make sure the necessary CrossSection variables are set
    xc.update_arrays()
    #run secant method to find adjustments for each target
    h_B_l, h_B_r, h_E_l, h_E_r = None, None, None, None
    if(B_l):
        h_B_l = _bisect(xc, conds, xc.lROWi, _B_funk, B_l, hlow, hhigh,
            max_iter, rel_err)
    if(B_r):
        h_B_r = _bisect(xc, conds, xc.rROWi, _B_funk, B_r, hlow, hhigh,
            max_iter, rel_err)
    if(E_l):
        h_E_l = _bisect(xc, conds, xc.lROWi, _E_funk, E_l, hlow, hhigh,
            max_iter, rel_err)
    if(E_r):
        h_E_r = _bisect(xc, conds, xc.rROWi, _E_funk, E_r, hlow, hhigh,
            max_iter, rel_err)
    #create return variables
    h = (h_B_l, h_B_r, h_E_l, h_E_r)
    adj = SectionBook('%s-height_adjusted' % xc.title)
    names = ['Adjusted_for_Bmax_left','Adjusted_for_Bmax_right',
            'Adjusted_for_Emax_left','Adjusted_for_Emax_right']
    titles = ['Bmax_l','Bmax_r','Emax_l','Emax_r']
    subtitles = ['Height Adjusted for %f mG at left ROW edge' % B_l,
                'Height Adjusted for %f mG at left ROW edge' % B_r,
                'Height Adjusted for %f kV/m at left ROW edge' % E_l,
                'Height Adjusted for %f kV/m at left ROW edge' % E_r]
    for n, t, s, a in zip(names, titles, subtitles, h):
        if(a is not None):
            #copy the input XC
            new_xc = copy.deepcopy(xc)
            #change the identification fields
            new_xc.name, new_xc.title, new_xc.subtitle = n, t, s
            #adjust conductor heights
            for idx in hot:
                new_xc.hot[idx].y += a
            for idx in gnd:
                new_xc.gnd[idx].y += a
            #store new_xc in the SectionBook
            adj.add_section(new_xc)
    #update everythin in the SectionBook
    adj.update()
    #deal with saving
    if('path' in kwargs):
        kwargs['save'] = True
    if('save' in kwargs):
        if(kwargs['save']):
            fn = _path_manage(xc.name + '_height_adjustments', 'xlsx', **kwargs)
            xl = pd.ExcelWriter(fn, engine = 'xlsxwriter')
            pd.DataFrame(data = list(h), index = names,
                columns = ['Height Addition (ft)']).to_excel(xl,
                sheet_name = 'Adjustments', index_label = 'Field - ROW Edge')
            adj.ROW_edge_export(xl = xl)
            for xc in adj:
                xc.fields.to_excel(xl, sheet_name = xc.name)
            xl.save()
            print('Optimal phasing results written to "%s"' % fn)

    return(h, adj)

def _bisect(xc, conds, sample_idx, funk, target, hlow, hhigh, max_iter, rel_err):
    #get sample x and y arrays with a single element in each
    x_sample = np.array([xc.x_sample[sample_idx]], dtype = float)
    y_sample = np.array([xc.y_sample[sample_idx]], dtype = float)
    #evaluate at the bracketing values
    flow = funk(hlow, target, xc, conds, x_sample, y_sample)
    fhigh = funk(hhigh, target, xc, conds, x_sample, y_sample)
    #check that the root is bracketed
    if(flow*fhigh > 0.):
        raise(fields_class.EMFError("""
        The root is not bracketed with an upper height adjustment limit
        of %g. Rootfinding with bisection can't be performed.
            f(h_0 = %g) = %g
            f(h_1 = %g) = %g""" % (hhigh, hlow, flow, hhigh, fhigh)))
    #evaluate at a midpoint
    hmid = (hhigh + hlow)/2.0
    fmid = funk(hmid, target, xc, conds, x_sample, y_sample)
    count = 1
    #iterate
    while((abs(fmid/target) > rel_err) and (count < max_iter)):
        #test and throw half out
        if(fmid*flow > 0.):
            hlow = hmid
        elif(fmid*fhigh > 0.):
            hhigh = hmid
        elif(fmid == 0.):
            return(hmid)
        #evaluate at middle
        hmid = (hhigh + hlow)/2.0
        fmid = funk(hmid, target, xc, conds, x_sample, y_sample)
        #increment
        count += 1
    #check if the iteration limit was hit
    if(count == max_iter):
        raise(fields_class.EMFError("""
        Failure in _bisection method. The iteration limit of %d was exceeded
        with a relative error threshold of %g. The final estimate was
        %g""" % (max_iter, rel_err, fmid)))
    return(hmid)

def _B_funk(h, target, xc, conds, x_sample, y_sample):
    #adjust conductor heights
    y = xc.y.astype(float, copy = True)
    y[conds] += h
    #calculate B field at ROW edge
    Bx, By = fields_calcs.B_field(xc.x, y, xc.I, xc.phase,
        x_sample, y_sample)
    Bx, By, Bprod, Bmax = fields_calcs.phasors_to_magnitudes(Bx, By)
    return(Bmax[0] - target)

def _E_funk(h, target, xc, conds, x_sample, y_sample):
    #adjust conductor heights
    y = xc.y.astype(float, copy = True)
    y[conds] += h
    #calculate E field at ROW edge
    Ex, Ey = fields_calcs.E_field(xc.x, y, xc.subconds, xc.d_cond,
        xc.d_bund, xc.V, xc.phase, x_sample, y_sample)
    Ex, Ey, Eprod, Emax = fields_calcs.phasors_to_magnitudes(Ex, Ey)
    return(Emax[0] - target)

def run(template_path, **kwargs):
    """Import the templates in an excel file with the path 'template_path'
    then generate a workbook of all fields results and lots of plots.
    Use the 'path' keyword argument to specify a destination for the output,
    otherwise it will be saved to the template's directory. Returns
    a SectionBook object.
    args:
        template_path - path to cross section template excel workbook
    kwargs:
        sheets - a list of sheet names to load, default is all sheets
        path - string, destination/filename for saved files
        format - string, saved plot format (usually 'png' or 'pdf')
        xmax - cutoff distance from ROW center in plots"""
    #force saving for the plotting functions if there is no 'path' keyword
    if(not ('path' in kwargs)):
        kwargs['save'] = True
        #also direct output files to the same directory as the template
        kwargs['path'] = os.path.dirname(template_path)
    #import templates
    sb = load_template(template_path)
    #export the full results workbook
    sb.results_export(**kwargs)
    #export ROW edge results
    sb.ROW_edge_export(**kwargs)
    #export single CrossSection plots
    for xc in sb:
        fig = fields_plots.plot_max_fields(xc, **kwargs)
        fields_plots.plt.close(fig)
    #export group comparison plots
    fields_plots.plot_groups(sb, **kwargs)
    return(sb)
