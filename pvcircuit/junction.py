# -*- coding: utf-8 -*-
"""
This is the PVcircuit Package. 
    pvcircuit.Junction()   # properties and methods for each junction
"""

import math   #simple math
import copy
from time import time
import numpy as np   #arrays
import matplotlib.pyplot as plt   #plotting
from scipy.optimize import brentq    #root finder
#from scipy.special import lambertw, gammaincc, gamma   #special functions
import scipy.constants as con   #physical constants
import ipywidgets as widgets
from IPython.display import display

# constants
k_q = con.k/con.e
DB_PREFIX = 2. * np.pi * con.e * (con.k/con.h)**3 / (con.c)**2 /1.e4    #about 1.0133e-8 for Jdb[A/cm2]
nan=np.nan

# Junction defaults
Eg_DEFAULT=1.1    #[eV]
TC_REF=25.0   #[C]
AREA_DEFAULT = 1.   #[cm2] note: if A=1, then I->J
BETA_DEFAUlT = 15.  # unitless

# numerical calculation parameters
VLIM_REVERSE=10.
VLIM_FORWARD=3.
VTOL= 0.0001
EPSREL=1e-15
MAXITER=1000

def TK(TC): return TC + con.zero_Celsius
    #convert degrees celcius to kelvin
         
class Junction(object):
    """
    Class for PV junctions.

    :param Rs: series resistance [ohms]
    """
    
    ATTR = ['Eg','TC','Gsh','Rser','lightarea','totalarea','Jext','JLC','beta','gamma','pn']          
    ARY_ATTR = ['n','J0ratio']
    J0scale = 1000. # mA same as Igor, changes J0ratio because of units

    def __init__(self, name='junc', Eg=Eg_DEFAULT, TC=TC_REF, \
                 Gsh=0., Rser=0., area=AREA_DEFAULT, \
                 n=[1.,2.], J0ratio=[10.,10.], J0ref=None, \
                 RBB=None, Jext=0.04, JLC=0., \
                 pn=-1, beta=BETA_DEFAUlT, gamma=0. ):
        
        # user inputs
        self.name = name    # remember my name
        self.Eg = np.float64(Eg)  #: [eV] junction band gap
        self.TC = np.float64(TC)  #: [C] junction temperature
        self.Jext = np.float64(Jext)   #: [A/cm2] photocurrent density
        self.Gsh = np.float64(Gsh)  #: [mho] shunt conductance=1/Rsh
        self.Rser = np.float64(Rser)  #: [ohm] series resistance
        self.lightarea = np.float64(area)   # [cm2] illuminated junction area
        self.totalarea = np.float64(area)   # [cm2] total junction area including shaded areas
        #used for tandems only
        self.pn = int(pn)     # p-on-n=1 or n-on-p=-1
        self.beta = np.float64(beta)    # LC parameter
        self.gamma = np.float64(gamma)    # PL parameter from Lan
        self.JLC = np.float64(JLC)   # LC current from other cell JLC=beta(this)*Jem(other)
        
        # multiple diodes
        # n=1 bulk, n=m SNS, and n=2/3 Auger mechanisms
        self.n = np.array(n)   #diode ideality list e.g. [n0, n1]
        if J0ref == None:
            self.J0ratio = np.array(J0ratio)    #diode J0/Jdb^(1/n) ratio list for T dependence            
        else:
            self._J0init(J0ref)  # calculate self.J0ratio from J0ref at current self.TC
         
        self.set(RBB=RBB) 

    def copy(self):
        '''
        create a copy of a Junction
        need deepcopy() to separate lists, dicts, etc but crashes
        '''
        
        return copy.copy(self)

    def __str__(self):
        #attr_list = self.__dict__.keys()
        #attr_dict = self.__dict__.items()
        #print(attr_list)
        
        strout = self.name+": <tandem.Junction class>"
                    
        strout += '\nEg = {0:.2f} eV, TC = {1:.1f} C' \
            .format(self.Eg, self.TC)
            
        strout += '\nJext = {0:.1f} , JLC = {1:.1f} mA/cm2' \
            .format( self.Jext*1000., self.JLC*1000.)

        strout += '\nGsh = {0:g} S/cm2, Rser = {1:g} Ωcm2' \
            .format(self.Gsh, self.Rser)
            
        strout += '\nlightA = {0:g} cm2, totalA = {1:g} cm2' \
            .format(self.lightarea, self.totalarea)
            
        strout += '\npn = {0:d}, beta = {1:g}, gamma = {2:g}' \
            .format(self.pn, self.beta, self.gamma, self.JLC)

        strout += '\n {0:^5s} {1:^10s} {2:^10s}' \
            .format('n','J0ratio', 'J0(A/cm2)')
        strout += '\n {0:^5s} {1:^10.0f} {2:^10.3e}' \
            .format('db', 1., self.Jdb)

        i=0
        for ideality_factor,ratio, saturation_current in zip(self.n, self.J0ratio, self.J0):
            strout += '\n {0:^5.2f} {1:^10.2f} {2:^10.3e}' \
                .format(self.n[i], self.J0ratio[i], self.J0[i])
            i+=1
        
        if self.RBB_dict['method'] :
            strout+=' \nRBB_dict: '+str(self.RBB_dict)
 
        return strout

    def __repr__(self):
        return str(self)

    '''
    def __setattr__(self, key, value):
        # causes problems
        super(Junction, self).__setattr__(key, value) 
        self.set(key = value)
    '''
    def set(self, **kwargs):
        for key, value in kwargs.items():
            if key == 'RBB':
                if value == 'JFG':
                    self.__dict__['RBB_dict'] =  {'method':'JFG', 'mrb':10., 'J0rb':0.5, 'Vrb':0.}
                elif value == 'bishop':
                    self.__dict__['RBB_dict'] = {'method':'bishop','mrb':3.28, 'avalanche':1., 'Vrb':-5.5}
                else:
                    self.__dict__['RBB_dict'] =  {'method': None}  #no RBB
            elif key == 'area':
                self.__dict__['lightarea'] = np.float64(value) 
                self.__dict__['totalarea'] = np.float64(value) 
            elif key == 'name': # strings
                self.__dict__[key] = str(value)
            elif key == 'pn': # integers
                self.__dict__[key] = int(value)
            elif key == 'RBB_dict':
                self.__dict__[key] = value
            elif key in ['n','J0ratio']: # array
                self.__dict__[key] = np.array(value)
            elif key == 'n[0]':
                self.n[0] =  np.float64(value)
            elif key == 'n[1]':
                self.n[1] =  np.float64(value)
            elif key == 'n[2]':
                self.n[2] =  np.float64(value)
            elif key == 'n[3]':
                self.n[3] =  np.float64(value)
            elif key == 'J0ratio[0]':
                self.J0ratio[0] =  np.float64(value)
            elif key == 'J0ratio[1]':
                self.J0ratio[1] =  np.float64(value)
            elif key == 'J0ratio[2]':
                self.J0ratio[2] =  np.float64(value)
            elif key == 'J0ratio[3]':
                self.J0ratio[3] =  np.float64(value)
            else: # scalar float
                self.__dict__[key] = np.float64(value)

    @property
    def Jphoto(self): return self.Jext * self.lightarea / self.totalarea + self.JLC 
        # total photocurrent
        # external illumination is distributed over total area
               
    @property
    def TK(self): return TK(self.TC)

    @property
    def Vth(self): return k_q * self.TK
        #Thermal voltage in volts = kT/q

    @property
    def Jdb(self):
        """
        detailed balance saturation current
        """
 
        EgkT = self.Eg / self.Vth
        
        #Jdb from Geisz et al.
        return DB_PREFIX * self.TK**3. * (EgkT*EgkT + 2.*EgkT + 2.) * np.exp(-EgkT)    #units from DB_PREFIX
    
    @property
    def J0(self):
        '''
        dynamically calculated J0(T)
        return np.ndarray [J0(n0), J0(n1), etc]
        '''
        
        if (type(self.n) is np.ndarray) and (type(self.J0ratio) is np.ndarray):
            if self.n.size == self.J0ratio.size:
                return (self.Jdb * self.J0scale)**(1./self.n) * self.J0ratio / self.J0scale 
            else:
                return np.nan   # different sizes
        else:
           return np.nan    # not numpy.ndarray
    
    def _J0init(self,J0ref):
        '''
        initialize self.J0ratio from J0ref
        return np.ndarray [J0(n0), J0(n1), etc]
        '''
        J0ref = np.array(J0ref)
        if (type(self.n) is np.ndarray) and (type(J0ref) is np.ndarray):
            if self.n.size == J0ref.size:
                self.J0ratio = self.J0scale * J0ref / (self.Jdb * self.J0scale)**(1./self.n)
                return 0   # success
            else:
                return 1   # different sizes
        else:
           return 2    # not numpy.ndarray
    
    def Jem(self,Vmid):
        '''
        light emitted from junction by reciprocity
        quantified as current density
        '''
        if Vmid > 0.:
            Jem = self.Jdb  * (np.exp(Vmid / self.Vth) - 1.)  # EL Rau
            Jem += self.gamma * self.Jphoto   # PL Lan and Green
            return Jem
        else:
            return 0.

    def notdiode(self):
        '''
        is this junction really a diode
        or just a resistor
        sum(J0) = 0 -> not diode
        pn = 0 -> not diode
        '''
        if self.pn == 0:
            return True
            
        jsum = np.float64(0.)
        for saturation_current in self.J0:
            jsum +=saturation_current
            
        return (jsum == np.float64(0.))
        
    def Jmultidiodes(self,Vdiode):
        '''
        calculate recombination current density from 
        multiple diodes self.n, self.J0 numpy.ndarray
        two-diodes:
        n  = [1, 2]  #two diodes
        J0 = [10,10]  #poor cell
        detailed balance:
        n  = [1]
        J0 = [1]
        three-diodes
        n = [1, 1.8, (2/3)]
        '''     
        Jrec = np.float64(0.)
        for ideality_factor, saturation_current in zip(self.n, self.J0):
            if ideality_factor>0. and math.isfinite(saturation_current):
                try:
                    Jrec += saturation_current \
                        * (np.exp(Vdiode / self.Vth / ideality_factor) - 1.)
                except:
                    continue
     
        return Jrec        

    def JshuntRBB(self, Vdiode):
        '''
        return shunt + reverse-bias breakdown current
    
            RBB_dict={'method':None}   #None
    
            RBB_dict={'method':'JFG', mrb'':10., 'J0rb':1., 'Vrb':0.}
    
            RBB_dict={'method':'bishop','mrb'':3.28, 'avalanche':1, 'Vrb':-5.5}
    
            RBB_dict={'method':'pvmismatch','ARBD':arbd,'BRBD':brbd,'VRBD':vrb,'NRBD':nrbd:
    
        Vdiode without Rs
        Vth = kT
        Gshunt
        '''
         
        RBB_dict = self.RBB_dict
        method=RBB_dict['method']
        JRBB=np.float64(0.)
        
        if method=='JFG' :
            Vrb=RBB_dict['Vrb']
            J0rb=RBB_dict['J0rb']
            mrb=RBB_dict['mrb']
            if Vdiode <= Vrb and mrb != 0. : 
                #JRBB = -J0rb * (self.Jdb)**(1./mrb) * (np.exp(-Vdiode / self.Vth / mrb) - 1.0)
                JRBB = -J0rb * (self.Jdb*1000)**(1./mrb) / 1000. \
                   * (np.exp(-Vdiode / self.Vth / mrb) - 1.0)
            
        elif method=='bishop':
            Vrb=RBB_dict['Vrb']
            a=RBB_dict['avalanche']
            mrb=RBB_dict['mrb']
            if Vdiode <= 0. and Vrb !=0. :  
                JRBB =  Vdiode * self.Gsh  * a * (1. - Vdiode / Vrb)**(-mrb)
                 
        elif method=='pvmismatch':
            JRBB=np.float64(0.) 
            
    
        return Vdiode * self.Gsh + JRBB
    
    def Jparallel(self,Vdiode,Jtot):
        '''
        circuit equation to be zeroed to solve for Vi
        for voltage across parallel diodes with shunt and reverse breakdown
        '''

        if self.notdiode():  # sum(J0)=0 -> no diode
            return Jtot

        JLED = self.Jmultidiodes(Vdiode)
        JRBB = self.JshuntRBB(Vdiode)
        #JRBB = JshuntRBB(Vdiode, self.Vth, self.Gsh, self.RBB_dict)
        return Jtot - JLED  - JRBB

    def Vdiode(self,Jdiode):
        '''
        Jtot = Jphoto + J
        for junction self of class Junction
        return Vdiode(Jtot)
        no Rseries here
        '''

        if self.notdiode():  # sum(J0)=0 -> no diode
            return 0.

        Jtot = self.Jphoto + Jdiode
        
        try: 
            Vdiode = brentq(self.Jparallel, -VLIM_REVERSE, VLIM_FORWARD, args=(Jtot),
                           xtol=VTOL, rtol=EPSREL, maxiter=MAXITER,
                           full_output=False, disp=True)
        except:
            return np.nan
            #print("Exception:",err)
                    
        return Vdiode

    def _dV(self, Vmid, Vtot):
        '''
        see singlejunction
        circuit equation to be zeroed (returns voltage difference) to solve for Vmid
        single junction circuit with series resistance and parallel diodes
        '''
        
        J = self.Jparallel(Vmid, self.Jphoto)
        dV = Vtot - Vmid  + J * self.Rser
        return dV

    def Vmid(self,Vtot):
        '''
        see Vparallel
        find intermediate voltage in a single junction diode with series resistance
        Given Vtot=Vparallel + Rser * Jparallel
        '''

        if self.notdiode():  # sum(J0)=0 -> no diode
            return 0.
 
        try:        
            Vmid = brentq(self._dV, -VLIM_REVERSE, VLIM_FORWARD, args=(Vtot),
                           xtol=VTOL, rtol=EPSREL, maxiter=MAXITER,
                           full_output=False, disp=True)
           
        except:
            return np.nan
            #print("Exception:",err)
      
        return Vmid 
 
    def controls(self):
        '''
        use interactive_output for GUI in IPython
        '''
        
        cell_layout = widgets.Layout(display='inline_flex',
                            flex_flow='row',
                            justify_content='flex-end',
                            width='180px')  
        # controls 
        in_name = widgets.Text(value=self.name,description='name',layout=cell_layout)                        
        in_Eg = widgets.BoundedFloatText(value=self.Eg, min=0.1,max=3.0,step=0.1,
            description='Eg (eV)',layout=cell_layout)
        in_TC = widgets.BoundedFloatText(value=self.TC, min=0., max=500.,step=0.1,
            description='T (°C)',layout=cell_layout)
        in_Jext = widgets.BoundedFloatText(value=self.Jext, min=0., max=.080,step=0.001,
            description='Jext (A/cm2)',layout=cell_layout)
        in_JLC = widgets.BoundedFloatText(value=self.JLC, min=0., max=.080,step=0.001,
            description='JLC (A/cm2)',layout=cell_layout)
        in_Gsh = widgets.BoundedFloatText(value=self.Gsh, min=0. ,step=0.1,
            description='Gsh (S/cm2)',layout=cell_layout)
        in_Rser= widgets.BoundedFloatText(value=self.Rser, min=0., step=0.1,
            description='Rser (Ωcm2)',layout=cell_layout)
        in_lightarea = widgets.BoundedFloatText(value=self.lightarea, min=1.e-6, max=1000.,step=0.1,
            description='Alight (cm2)',layout=cell_layout)
        in_totalarea = widgets.BoundedFloatText(value=self.totalarea, min=self.lightarea, max=1000.,step=0.1,
            description='Atotal (cm2)',layout=cell_layout)
        in_beta = widgets.BoundedFloatText(value=self.beta, min=0., max=50.,step=0.1,
            description='beta',layout=cell_layout)
        in_gamma = widgets.BoundedFloatText(value=self.gamma, min=0., max=3.0,step=0.1,
            description='gamma',layout=cell_layout)
        in_pn = widgets.BoundedIntText(value=self.pn,min=-1,max=1,
            description='pn',layout=cell_layout)
            
        #linkages
        arealink = widgets.dlink((in_lightarea,'value'), (in_totalarea,'min')) #also jsdlink works
            
        attr = ['name']+self.ATTR.copy()
        cntrls = [in_name, in_Eg,in_TC,in_Gsh,in_Rser,in_lightarea,in_totalarea,
                in_Jext,in_JLC,in_beta,in_gamma,in_pn]
        sing_dict = dict(zip(attr,cntrls))
        singout = widgets.interactive_output(self.set, sing_dict)

        def on_change(change):
            # function for changing values
            old = change['old'] #old value
            new = change['new'] #new value
            owner = change['owner'] #control
            value = owner.value
            desc = owner.description
            
            self.iout.clear_output()
            with self.iout: # output device
                print(desc, old, new)
                #print(change)
                #print(self)
                if owner == in_totalarea:
                   #print("in_totalarea",in_lightarea.value)
                   pass

        # diode array
        in_tit = widgets.Label(value='Junction')
        in_lab = widgets.Label(value='diodes:')
        diode_layout = widgets.Layout(flex_flow='column',align_items='center',width='100px')    
        
        cntrls.append(in_lab)
        in_n = []  # empty list of n controls
        in_ratio = [] # empty list of Jratio controls
        hui = []
        diode_dict = {} 
        for i in range(len(self.n)):
            in_n.append(widgets.BoundedFloatText(value=self.n[i], min=0.1, max=3.0, step=0.1,
                description='n['+str(i)+']',layout=cell_layout))
            in_ratio.append(widgets.BoundedFloatText(value=self.J0ratio[i], min=0, max=10000,
                description='J0ratio['+str(i)+']',layout=cell_layout))
            cntrls.append(in_n[i])
            cntrls.append(in_ratio[i])
            diode_dict['n['+str(i)+']'] = in_n[i]
            diode_dict['J0ratio['+str(i)+']'] = in_ratio[i]  
            #hui.append(widgets.HBox([in_n[i],in_ratio[i]])) 
            #cntrls.append(hui[i])
          
        diodeout = widgets.interactive_output(self.set, diode_dict)
       
        for cntrl in cntrls:
            cntrl.observe(on_change,names='value')

        #output
        self.iout = widgets.Output()
        self.iout.layout.height = '50px'
        cntrls.append(self.iout)
        
        # user interface        
        box_layout = widgets.Layout(display='flex',
                            flex_flow='column',
                            align_items='center',
                            border='1px solid black',
                            width='300px')
                            
        ui = widgets.VBox([in_tit] + cntrls,layout=box_layout)
        
        return ui
