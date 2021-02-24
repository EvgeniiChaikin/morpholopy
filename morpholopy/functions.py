import numpy as np

def calculate_kappa_co(halo_data, partsDATA, siminfo, halo_index):
    # subhalo contain subhalo data and is strutured as follow
    # [ (0:3)CentreOfPotential[kpc]: (0)X | (1)Y | (2)Z  | (3:6)Velocity[km/s]: (3)Vx | (4)Vy | (5)Vz  | (6)R200c[kpc]]
    # partsDATA contains particles data and is structured as follow
    # [ (:3)Position[kpc]: (0)X | (1)Y | (2)Z  | (3)Mass[Msun] | (4:7)Velocity[km/s]: (4)Vx | (5)Vy | (6)Vz | (7)hsml]
    
    particlesDATA = np.array(partsDATA).copy()                    # isolating a copy

    #particlesDATA[:,:3]-=subhalo[0:3].astype('float')-siminfo.boxSize/2   # centering onto subhalo CoP, and unwrap the box
    # Centering onto subhalo CoP
    particlesDATA[:, 0] -= halo_data.xminpot[halo_index]
    particlesDATA[:, 1] -= halo_data.yminpot[halo_index]
    particlesDATA[:, 2] -= halo_data.zminpot[halo_index]
    particlesDATA[:, :3] += siminfo.boxSize/2
    particlesDATA[:, :3] %=(siminfo.boxSize)
    particlesDATA[:, :3] -=siminfo.boxSize/2        # end the unwrap

    # Center velocities on the subhalo CoM velocity
    #particlesDATA[:,4:7]-=subhalo[3:6].astype('float')
    particlesDATA[:, 4] -= halo_data.vxminpot[halo_index]
    particlesDATA[:, 5] -= halo_data.vyminpot[halo_index]
    particlesDATA[:, 6] -= halo_data.vzminpot[halo_index]

    # Compute distances
    distancesDATA = np.linalg.norm(particlesDATA[:,:3],axis=1)

    # Restrict particles
    extract = distancesDATA<30.

    particlesDATA = particlesDATA[extract,:]
    distancesDATA = distancesDATA[extract]
    Mstar = np.sum(particlesDATA[:,3])                            #compute total in-aperture stellar mass

    # Compute 30kpc CoM to Sub CoM velocty offset & recenter
    dvVmass = np.sum(particlesDATA[:,3][:,np.newaxis]*particlesDATA[:,4:7],axis=0) / Mstar
    particlesDATA[:,4:7]-=dvVmass

    # Compute momentum
    smomentums = np.cross(particlesDATA[:,:3],particlesDATA[:,4:7])
    momentum = np.sum(particlesDATA[:,3][:,np.newaxis]*smomentums,axis=0)

    # Compute specific angular momentum
    sa_momentum = momentum / Mstar
    sa_momentum = np.linalg.norm(sa_momentum)
    
    # Compute rotational velocities
    smomentumz = np.sum(momentum*smomentums/np.linalg.norm(momentum),axis=1)
    cyldistances = np.sqrt(distancesDATA**2-np.sum(momentum*particlesDATA[:,:3]/np.linalg.norm(momentum),axis=1)**2)
    #cylmin = np.min(cyldistances[cyldistances>0])
    #cyldistances[cyldistances==0] = cylmin
    vrots = smomentumz / cyldistances
    
    # Compute kappa_co
    Mvrot2 = np.sum((particlesDATA[:,3]*vrots**2)[vrots>0])
    kappa_co = Mvrot2/np.sum(particlesDATA[:,3]*(np.linalg.norm(particlesDATA[:,4:7],axis=1))**2)
    
    # Apply rotation so that momentum vector corresponds to z-axis
    momentum /= np.linalg.norm(momentum)

    # Return
    return kappa_co, sa_momentum, momentum, particlesDATA


def AsymFrac(rs, ms, level=1):
    '''
        rs - CoM subtracted positions of *selected* particles in galactic units
        ms - *selected* particle masses in galactic units
        level - controls number of healpix bins, 1 as default
        '''
    pixlev     = level
    M          = ms.sum()
    nbins      = hpy.nside2npix(pixlev)
    binnum     = np.arange(nbins)
    binrs      = np.column_stack(hpy.pix2vec(pixlev,binnum))
    bindx      = hpy.vec2pix(pixlev, rs[:,0], rs[:,1], rs[:,2])
    bins       = [0, np.inf] # for now just look at mass in each bin, not mass dist.
    m_assym    = 0.
    
    for i in binnum[:nbins//2]:
        j   = hpy.vec2pix(pixlev, *-binrs[i])
        dx1 = bindx==i
        dx2 = bindx==j
        Rs1 = (rs[dx1]**2).sum(axis=-1)**0.5
        Rs2 = (rs[dx2]**2).sum(axis=-1)**0.5
        h1 = np.histogram(Rs1, bins=bins, weights=ms[dx1])[0]#/((4/3.)*np.pi*(bins[1:]**3 - bins[:-1]**3))
        h2 = np.histogram(Rs2, bins=bins, weights=ms[dx2])[0]#/((4/3.)*np.pi*(bins[1:]**3 - bins[:-1]**3))
        m_assym += np.sum(np.abs(h1-h2))
    
    return m_assym/M

class GravPot():
    def __init__(self, ds, ms):
        '''
            ds - CoM subtracted distances of all particles in the aperture selection in galactic units
            ms - particle masses of all particles in galactic units
            '''
        
        G.convert_to_base('galactic')
        sortd   = ds.argsort()
        m_i     = ms[sortd][1:]
        self.d_t   = ds[sortd][1:]
        self.m_t   = np.cumsum(m_i)
        self.jc_t  = pow(G * self.m_t * self.d_t, 0.5)
        
        pot_2 = m_i / self.d_t
        pot_2 = pot_2[::-1].cumsum()[::-1]
        
        self.pot_t = -G*self.m_t/self.d_t - G*pot_2
        self.E_t   = G*self.m_t/(2*self.d_t) + self.pot_t
        
        #cheap velocities
        self.v_func = interp1d(self.d_t, np.sqrt(G*self.m_t/self.d_t), fill_value='extrapolate')
    
    def calcEtot(self, vel, r):
        '''
            vel - velocities of *selected* particles in galactic units
            r - CoM subtracted positions of *selected* particles in galactic units
            '''
        v2 = np.sum(vel**2, axis=1)
        pot = np.interp(r, self.d_t, self.pot_t)
        return 0.5*v2 + pot
    
    def calcJcirc(self, E):
        "E - total energy output by above function "
        return np.interp(E, self.E_t, self.jc_t)

def AxialRatios(rs, ms):
    '''
        rs - CoM subtracted positions of *selected* particles in galactic units
        ms - *selected* particle masses in galactic units
        zaza'''
    radius = np.linalg.norm(rs[:, :3], axis=1)
    rs = rs[radius>0,:]
    ms = ms[radius>0]
    rs2 = rs**2

    # construct MoI tensor
    I_xx                    = ((rs2[:,[1,2]].sum(axis=-1) / abs((rs2[:,[1,2]].sum(axis=-1))**0.5))*ms)
    I_xx = I_xx[np.isnan(I_xx)==False]     # remove nans
    I_xx = I_xx.sum()
    I_yy                    = ((rs2[:,[0,2]].sum(axis=-1) / abs((rs2[:,[0,2]].sum(axis=-1))**0.5))*ms)
    I_yy = I_yy[np.isnan(I_yy)==False]
    I_yy = I_yy.sum()
    I_zz                    = ((rs2[:,[0,1]].sum(axis=-1) / abs((rs2[:,[0,1]].sum(axis=-1))**0.5))*ms)
    I_zz = I_zz[np.isnan(I_zz)==False]
    I_zz = I_zz.sum()
    I_xy                    = -((rs[:,0]*rs[:,1] / abs(rs[:,0]*rs[:,1])**0.5)*ms)
    I_xy = I_xy[np.isnan(I_xy)==False]
    I_xy = I_xy.sum()
    I_xz                    = -((rs[:,0]*rs[:,2] / abs(rs[:,0]*rs[:,2])**0.5)*ms)
    I_xz = I_xz[np.isnan(I_xz)==False]
    I_xz = I_xz.sum()
    I_yz                    = -((rs[:,1]*rs[:,2] / abs(rs[:,1]*rs[:,2])**0.5)*ms)
    I_yz = I_yz[np.isnan(I_yz)==False]
    I_yz = I_yz.sum()
    I                       = np.array([[I_xx, I_xy, I_xz], [I_xy, I_yy, I_yz], [I_xz, I_yz, I_zz]])

    # Get and order eigenvalues
    W,V                   = np.linalg.eig(I)
    W1, W2, W3            = np.sort(W)[::-1]

    # compute axes (unnormalised as we don't need absolute values)
    a                     = np.sqrt(np.abs(W1 + W2 - W3))
    b                     = np.sqrt(np.abs(W1 + W3 - W2))
    c                     = np.sqrt(np.abs(W2 + W3 - W1))
    
    return c/a, c/b, b/a

def DiscFraction(ms, jzs):
    '''
        rs - CoM subtracted positions of *selected* particles in galactic units
        ms - *selected* particle masses in galactic units
        '''
    counterrots = ms[np.array(jzs) < 0]
    bfrac = (2 * counterrots.sum())/ms.sum()
    dmass = np.clip(1. - bfrac, 0.,  1.)
    return dmass

def Epsilon(rs, ms, vs, jzs, gpot):
    '''
        rs - CoM subtracted positions of *selected* particles in galactic units
        ms - *selected* particle masses in galactic units
        vs - *selected* particle velocities in galactic units
        jzs - *selected* particle specific angular momentum in the spin axis direction
        gpot - GravPot() object for the Halo
        '''
    Etots = gpot.calcEtot(vs, np.sqrt(np.sum(rs**2, axis=1)))
    j_circs = gpot.calcJcirc(Etots)
    return jzs/j_circs
