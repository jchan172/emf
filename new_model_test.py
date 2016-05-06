import numpy as np
import matplotlib.pyplot as plt
import csv

class FLDError(Exception):
    def __init__(self, message):
        self.message = message
    def __str__(self):
        return(self.message)

def Crout_backward_substitution(A,b):
    #back substitution with the diagonal elements of the matrix set to 1
    n = len(b)
    x = np.empty((n,))
    for i in range(n-1,-1,-1):
        x[i] = b[i] - sum([A[i,j]*x[j] for j in range(i+1,n)])
    return(x)

def forward_substitution(A,b):
    #perform forward substitution to solve a lower triangular matrix equation
    n = len(b)
    x = np.empty((n,))
    for i in range(n):
        x[i] = (b[i] - sum([A[i,j]*x[j] for j in range(i)]))/float(A[i,i])
    return(x)

def Crout_factorization(A):
    #Crout LU matrix decomposition, returning a single matrix storing L and U
    M = A[:,:]
    n = A.shape[0]
    LU = np.empty((n,n))
    #factorize
    for i in range(n):
        #fill in a column of L
        for j in range(i,n):
            LU[j,i] = A[j,i] - sum([LU[j,k]*LU[k,i] for k in range(j)])
        #fill in a row of U
        for j in range(i+1,n):
            LU[i,j] = (A[i,j] - sum([LU[i,k]*LU[k,j] for k in range(i)]))/LU[i,i]
    return(LU)

def E_field(f_cond, x_cond, y_cond, subconds, d_cond, d_bund, V_cond, I_cond, p_cond, x, y):
    """Calculate the approximate electric field generated by a group of
    conductors. Each of the variables labeled '_cond' should be an numpy
    array of parameters, where each index in those arrays describes a
    unique conductor, i.e. the 0th value in each variable is attributed to
    one power line."""

    #check lengths of x and y
    if(len(x) != len(y)):
        raise(FLDError('Inputs x and y must have the same lenghts, forming x-y pairs.'))

    #Define a time interval with the maximum amount of time required to
    #complete one cycle (the period).
    if(any(np.diff(f_cond))):
        raise(FLDError('At least one input frequency is different than the others. Calculations assume they are uniform.'))
    T = 1./f_cond[0]
    t = np.linspace(0, T, 1001)

    #convenient variables/constants
    epsilon = 8.854e-12
    C = 1./(2.*np.pi*epsilon)
    L = len(t)          #number of time steps
    N = len(f_cond)     #number of conductors
    Z = len(x)          #number of sample points or x,y pairs

    #calculate the effective conductor diameters
    d_cond  = d_bund*((subconds*d_cond/d_bund)**(1./subconds))

    #conversions
    w_cond = 2*np.pi*f_cond/360.    #convert to radians
    x_cond *= 0.3048                #convert to meters
    y_cond *= 0.3048                #convert to meters
    d_cond *= 0.0254                #convert to meters
    V_cond *= 1./np.sqrt(3)         #convert to ground reference from line-line
                                    #reference
    p_cond *= 2*np.pi/360.          #convert to radians
    x       = x*0.3048              #convert to meters
    y       = y*0.3048              #convert to meters

    #compute the potential coefficient matrix
    P = np.empty((N,N))
    #diagonals
    for i in range(N):
        P[i,i] = C*np.log(4*y_cond[i]/d_cond[i])
    #other elements
    for i in range(N):
        for j in range(N):
            if(i != j):
                n = (x_cond[i] - x_cond[j])**2 + (y_cond[i] + y_cond[j])**2
                d = (x_cond[i] - x_cond[j])**2 + (y_cond[i] - y_cond[j])**2
                P[i,j] = C*n/d
    #Crout LU decomposition of the P matrix
    P_LU = Crout_factorization(P)

    #Compute time dependent voltage signals. Each column represents the signal
    #for a conductor, with rows representative of the different times.
    V = np.empty((L,N))
    for i in range(N):
        V[:,i] = V_cond[i]*np.cos(w_cond[i]*t + p_cond[i])

    #Compute the charge, same format as the 'V' with each conductor in a column.
    #Each time represents a different voltage configuration of all the
    #conductors. Solve the matrix equation P Q = V for each time step.
    Q = np.empty((L,N))
    for i in range(L):
        M = forward_substitution(P_LU, V[i,:])
        Q[i,:] = Crout_backward_substitution(P_LU, M)

    #Compute the x and y components of the electric field. The columns (1st
    #dimension) of the arrays represent x,y pairs and the rows represent
    #times or charge configurations
    E_x = np.zeros((L,Z))
    E_y = np.zeros((L,Z))
    for i in range(Z): #x,y pairs
        for j in range(L): #time steps
            for k in range(N): #conductors
                #x component
                nx = C*Q[j,k]*(x_cond[k] - x[i])
                d1 = (x_cond[k] - x[i])**2 + (y_cond[k] - y[i])**2
                d2 = (x_cond[k] - x[i])**2 + (y_cond[k] + y[i])**2
                E_x[j,i] += nx/d1 - nx/d2
                #y component
                ny1 = C*Q[j,k]*(y_cond[k] - y[i])
                ny2 = C*Q[j,k]*(y_cond[k] + y[i])
                E_y[j,i] += ny1/d1 - ny2/d2

    #compute resultant field magnitude
    #E = np.sqrt(E_x**2 + E_y**2)

    return(E_x, E_y)

#sample locations
x = np.arange(-25, 26)
y = 3*np.ones((len(x),))

#conductor properties 1
f_cond = np.array([60,60])     #frequency (degrees)
x_cond = np.array([-5.,5.])    #x coordinate (feet)
y_cond = np.array([20.,30.])    #y coordinate (feet)
subconds = np.array([2.,1.])   #number of subconductors
d_cond = np.array([1.04,.56])   #diameter (inches)
d_bund = np.array([2.,.56])
V_cond = np.array([345.,300.])   #phase-phase voltage (kV)
I_cond = np.array([241.,420.])   #phase current (amp)
p_cond = np.array([0.,120.])    #phase angle (degrees)

E_x,E_y = E_field(f_cond, x_cond, y_cond, subconds, d_cond, d_bund, V_cond, I_cond, p_cond, x, y)

#calculate resultant fields
E = np.sqrt(E_x**2 + E_y**2)

#find the maxamum values at each point through time
N = E.shape[1]
E_max = np.zeros((N,))
for i in range(N):
    E_max[i] = max(E[:,i])

print(E_max)

#export the maximum values
with open('temp.csv','w') as ofile:
    writer = csv.writer(ofile)
    writer.writerows(zip(x,y,E_max))

#plot the maxima at each point
plt.plot(x, E_max, 'bo')

plt.savefig('test_plot.png')
