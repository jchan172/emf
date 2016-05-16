import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from os import path

import emf_funks
import emf_plots
import emf_calcs

class EMFError(Exception):
    """Exception class for emf specific errors"""

    def __init__(self, message):
        self.message = message
    def __str__(self):
        return(self.message)

class Conductor:
    """Class representing a single conductor or power line."""

    def __init__(self):
        self.tag = None #conductor label
        self.freq = 60. #phase frequency
        self.x = None #x coordinate
        self.y = None #y coordinate
        self.subconds = None #number of subconductors per bundle
        self.d_cond = None #conductor diameter
        self.d_bund = None #bundle diameter
        self.V = None #line voltage
        self.I = None #line current
        self.phase = None #phase angle

    def __str__(self):
        """quick and dirty printing"""
        v = vars(self)
        keys = v.keys()
        s = '\n'
        for k in keys:
            s += str(k) + ': ' + str(v[k]) + '\n'
        return(s)

class CrossSection:
    """Class that organizes Conductor objects and stores other input
    information for a power line cross section. Includes plotting methods
    for the fields results and exporting methods for the results."""

    def __init__(self, name):
        self.name = name #mandatory, short, generally template sheet name
        self.title = '' #longer form, used for ploting text
        self.tag = None #identifier linking multiple CrossSection objects
        self.subtitle = '' #any extra information
        self.soil_resistivity = 100. #?
        self.max_dist = None #maximum simulated distance from the ROW center
        self.step = None #step size for calculations
        self.sample_height = 3. #uniform sample height
        self.lROW = None #exact coordinate of the left ROW edge
        self.lROWi = None #self.fields index closest to self.lROW
        self.rROW = None #exact coordinate of the left ROW edge
        self.rROWi = None #self.fields index closest to self.rROW
        self.hot = [] #list of Conductor objects with nonzero voltage
        self.gnd = [] #list of Conductor objects with zero voltage
        self.fields = pd.DataFrame(columns = ['Bx','By','Bprod','Bmax',
                                            'Ex','Ey','Eprod','Emax'])

    def __str__(self):
        """quick and dirty printing"""
        v = vars(self)
        keys = v.keys()
        s = '\n'
        for k in keys:
            if(k != 'fields'):
                s += str(k) + ': ' + str(v[k]) + '\n'
        s += '\ninspect self.fields separately to see field simulation results\n'
        return(s)

    def fetch(self, v):
        """Collect variables from all Conductors stored in the CrossSection
        into a numpy array, using the variable name as a string.
        args:
            v - string, variable name to fetch"""
        if(not (v in vars(Conductor()).keys())):
            raise(EMFError('"%s" is not a Conductor class variable, could not be fetched.'))
        a = []
        for c in (self.hot + self.gnd):
            exec('a.append(c.' + v + ')')
        return(np.array(a))

    def calculate_fields(self):
        """Calculate electric and magnetic fields across the ROW and store the
        results in the self.fields DataFrame"""
        #calculate sample points
        N = 1 + 2*self.max_dist/self.step
        x = np.linspace(-self.max_dist, self.max_dist, num = N)
        y = self.sample_height*np.ones((N,))
        #assemble all the conductor data in arrays for calculations
        conds = self.hot + self.gnd
        x_c, y_c = np.array([c.x for c in conds]), np.array([c.y for c in conds])
        subc = np.array([c.subconds for c in conds])
        d_c = np.array([c.d_cond for c in conds])
        d_b = np.array([c.d_bund for c in conds])
        V, I = np.array([c.V for c in conds]), np.array([c.I for c in conds])
        ph = np.array([c.phase for c in conds])
        #calculate electric field
        Ex, Ey = emf_calcs.E_field(x_c, y_c, subc, d_c, d_b, V, ph, x, y)
        Ex, Ey, Eprod, Emax = emf_funks.phasors_to_magnitudes(Ex, Ey)
        #calculate magnetic field
        Bx, By = emf_calcs.B_field(x_c, y_c, I, ph, x, y)
        Bx, By, Bprod, Bmax = emf_funks.phasors_to_magnitudes(Bx, By)
        #store the values
        self.fields = pd.DataFrame({'Ex':Ex,'Ey':Ey,'Eprod':Eprod,'Emax':Emax,
                                    'Bx':Bx,'By':By,'Bprod':Bprod,'Bmax':Bmax},
                                    index = x)
        #update ROW edge index variables
        #if ROW edge lies between two sample points, use the one closer to zero
        d = np.absolute((self.fields.index - self.lROW).values)
        self.lROWi = max(self.fields.index[d == np.min(d)])
        #if ROW edge lies between two sample points, use the one closer to zero
        d = np.absolute((self.fields.index - self.rROW).values)
        self.rROWi = min(self.fields.index[d == np.min(d)])
        #return the fields dataframe
        return(self.fields)

    def optimize_phasing(self):
        """Permute the phasing of the non-grounded conductors and find the
        arrangement that results in the lowest fields at the left and right
        edge of the ROW. The number of hot conductors must be a multiple of
        three. The phases of consecutive groups of three conductors are
        swapped around, assuming that those groups represent a single
        three-phase transfer circuit."""
        #check the number of hot lines
        if(self.N_hot % 3 != 0):
            raise(EMFError('The number of hot (not grounded) conductors must be a multiple of three.'))
        #number of 3 phase groups
        G = self.N_hot/3
        #number of permutations
        N = 6*G
        #all permutations of a single three phase group
        perm = [[0,1,2],[0,2,1],[1,0,2],[1,2,0],[2,0,1],[2,1,0]]
        #variables to store results of permutations
        #
        #...to be continued?

    def compare_DAT(self, DAT_path, **kwargs):
        """Load a FIELDS output file (.DAT), find absolute and percentage
        differences between it and the CrossSection objects results,
        write them to an excel file and generate comparative plots. The
        default excel file name is the CrossSection's title with
        '-DAT_comparison' appended to it.
        args:
            DAT_path - path of FIELDS results file
        kwargs:
            path - string, destination saved files
            round - int, round the results in self.fields to a certain
                    number of digits in an attempt to exactly match the
                    FIELDS results, which are printed only to the
                    thousandths digit
            truncate - bool, truncate results after the thousandths digit"""
        #load the .DAT file into a dataframe
        df = pd.read_table(DAT_path, skiprows = [0,1,2,3,4,5,6],
                            delim_whitespace = True, header = None,
                            names = ['Bx', 'By', 'Bprod', 'Bmax',
                                    'Ex', 'Ey', 'Eprod', 'Emax'],
                            index_col = 0)
        #check dataframe shape compatibility
        if(df.shape != self.fields.shape):
            raise(EMFError('self.fields in CrossSection named "%s" and the imported .DAT DataFrame have different shapes. Be sure to target the correct .DAT file and that it has compatible DIST values.' % self.name))
        #prepare a dictionary to create a Panel
        keys = kwargs.keys()
        if(('round' in keys) and ('truncate' in keys)):
            raise(FLDError('Cannot both round and truncate for DAT comparison. Choose either rounding or truncation.'))
        elif('round' in keys):
            f = self.fields.round(kwargs['round'])
        elif('truncate' in keys):
            if(kwargs['truncate']):
                f = self.fields.copy(deep = True)
                for c in f.columns:
                    for i in f.index:
                        f[c].loc[i] = float('%.3f' % f[c].loc[i])
        else:
            f = self.fields
        comp = {'FIELDS_output' : df,
                'New_model_output' : f,
                'Absolute Difference' : f - df,
                'Percent Difference' : 100*(f - df)/f}
        #write the frames to a spreadsheet
        fn = emf_funks.path_manage(self.name + '-DAT_comparison', '.xlsx', **kwargs)
        pan = pd.Panel(data = comp)
        pan.to_excel(fn, index_label = 'x')
        print('DAT comparison book saved to: %s' % fn)
        #make plots of the absolute and percent error
        figs = emf_plots.plot_DAT_comparison(self, pan, **kwargs)

class SectionBook:
    """Top level class organizing a group of CrossSection objects. Uses a
    dictionary to track CrossSections in a list and provide a convenient
    __getitem__ method than gets CrossSections by their name. Also tracks
    maximum field results at the ROW edges of each CrossSection added,
    provides a plotting method for CrossSection groups, and provides
    exporting methods."""

    def __init__(self, name):
        self.name = name #mandatory identification field
        self.xcs = [] #list of cross section objects
        self.name2idx = dict() #mapping dictionary for CrossSection retrieval
        self.names = [] #list of CrossSection names
        self.tags = [] #collection of CrossSection tags
        self.tag_groups = [[]] #groups of CrossSection indices with identical tags
        #DataFrame of maximum fields at ROW edges
        self.ROW_edge_max = pd.DataFrame(columns = ['name','title',
                                            'Bmaxl','Bmaxr','Emaxl','Emaxr'])

    def __getitem__(self, key):
        """Index the SectionBook by CrossSection names"""
        try:
            idx = self.name2idx[key]
        except(KeyError):
            return(False)
        else:
            return(self.xcs[idx])

    def __iter__(self):
        """Iteration over all CrossSections in the SectionBook"""
        for xc in self.xcs:
            yield(xc)

    def __len__(self):
        """Length of SectionBook is the number of CrossSections in it"""
        return(len(self.xcs))

    def __str__(self):
        """quick and dirty printing"""
        v = vars(self)
        keys = v.keys()
        s = '\n'
        for k in keys:
            s += str(k) + ': ' + str(v[k]) + '\n'
        return(s)

    def i(self, idx):
        """Get a CrossSection object by it's numeric index in self.xcs"""
        return(self.xcs[idx])

    def add_section(self, xc):
        """Add a CrossSection to the book. Doing so by directly altering
        self.xcs will make the CrossSections inaccessible by __getitem__
        and make the group plotting functions impossible, so don't do that
        and use this method instead."""
        #Prevent adding CrossSections with the same names
        if(xc.name in self.names):
            raise(EMFError('CrossSection name "%s" already exists in the SectionBook. Duplicate names would cause collisions in the lookup dictionary (self.name2idx). Use a different name.' % xc.name))
        else:
            self.name2idx[xc.name] = len(self.xcs)
            self.xcs.append(xc)
            self.names.append(xc.name)
            self.tags.append(xc.tag)

    def ROW_edge_export(self, **kwargs):
        """Write max field results at ROW edges for each cross section to
        an excel or csv file. Default is csv.
        kwargs:
            file_type - string, accepts 'csv' or 'excel'
            path - string, destination/filename for saved file"""
        #be sure ROW_edge_results are current
        #self.compile_ROW_edge_results()
        #export
        c = ['name','title','Bmaxl','Emaxl','Bmaxr','Emaxr']
        h = ['Name','Title','Bmax - Left ROW Edge','Emax - Left ROW Edge',
                'Bmax - Right ROW Edge','Emax - Right ROW Edge']
        excel = False
        if('file_type' in kwargs.keys()):
            if(kwargs['file_type'] == 'excel'):
                excel = True
        if(excel):
            fn = emf_funks.path_manage(self.name + '-ROW_edge_results', '.xlsx', **kwargs)
            self.ROW_edge_max.to_excel(fn, index = False, columns = c,
                                    header = h, sheet_name = 'ROW_edge_max')
        else:
            fn = emf_funks.path_manage(self.name + '-ROW_edge_results', '.csv', **kwargs)
            self.ROW_edge_max.to_csv(fn, index = False, columns = c, header = h)
        print('Maximum fields at ROW edges written to: "%s"' % fn)

    def full_export(self, **kwargs):
        """Write all of the cross section results to an excel workbook"""
        #path management
        fn = emf_funks.path_manage(self.name + '-full_results', '.xlsx', **kwargs)
        #data management
        xlwriter = pd.ExcelWriter(fn, engine = 'xlsxwriter')
        for xc in self:
            xc.fields.to_excel(xlwriter, sheet_name = xc.name)
        print('Full SectionBook results written to: "%s"' % fn)

    #---------------------------------------------------------------------------
    #functions that update SectionBook variables when CrossSections are done
    #being added or when CrossSection data changes

    def update(self):
        """Executes all of the update functions"""
        self.update_tag_groups()
        self.update_ROW_edge_max()

    def update_tag_groups(self):
        """Generate a list of lists of CrossSection indices with the same tag"""
        u = list(set(self.tags)) #get unique CrossSection tags
        self.tag_groups = [[] for i in range(len(u))]
        for i in range(len(self.xcs)):
            self.tag_groups[u.index(self.xcs[i].tag)].append(i)

    def update_ROW_edge_max(self):
        """Execution populates the self.ROW_edge_max DataFrame with
        the most current results of the fields calculation in each
        CrossSection."""
        #gather ROW edge results
        L = len(self.xcs)
        El,Er,Bl,Br = np.zeros((L,)),np.zeros((L,)),np.zeros((L,)),np.zeros((L,))
        titles = []
        for i in range(L):
            xc = self.i(i)
            Bl[i] = xc.fields['Bmax'][xc.lROWi]
            Br[i] = xc.fields['Bmax'][xc.rROWi]
            El[i] = xc.fields['Emax'][xc.lROWi]
            Er[i] = xc.fields['Emax'][xc.rROWi]
            titles.append(xc.title)
        #construct DataFrame
        data = {'name' : self.names, 'title' : titles,
                'Bmaxl' : Bl, 'Emaxl' : El, 'Bmaxr' : Br, 'Emaxr' : Er}
        self.ROW_edge_max = pd.DataFrame(data = data).sort_values('name')
