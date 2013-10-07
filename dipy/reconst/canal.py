import numpy as np
from dipy.reconst.cache import Cache
from dipy.reconst.multi_voxel import multi_voxel_fit
from dipy.reconst.shm import real_sph_harm
from dipy.core.gradients import gradient_table
from scipy.special import genlaguerre, gamma, hyp2f1
from dipy.core.geometry import cart2sphere
from math import factorial


class AnalyticalModel(Cache):

    def __init__(self, gtab):
        r""" Analytical and continuous modeling of the diffusion signal

        The main idea is to model the diffusion signal as a linear combination of continuous
        functions $\phi_i$,

        ..math::
            :nowrap:
                \begin{equation}
                    S(\mathbf{q})= \sum_{i=0}^I  c_{i} \phi_{i}(\mathbf{q}).
                \end{equation}

        where $\mathbf{q}$ is the wavector which corresponds to different gradient directions.
        Numerous continuous functions $\phi_i$ can be used to model $S$. Some are presented in
        [1,2,3]_.

        From the $c_i$ coefficients, there exist analytical formulae to estimate the ODF.

        This is an abstract class, which is used as a template for the implementation
        of specific continuous functions classe.

        Parameters
        ----------
        gtab : GradientTable,
            Gradient directions and bvalues container class


        References
        ----------
        .. [1] Merlet S. et. al, "Continuous diffusion signal, EAP and ODF estimation via
        Compressive Sensing in diffusion MRI", Medical Image Analysis, 2013.

        .. [2] Rathi Y. et. al, "Sparse multi-shell diffusion imaging", MICCAI, 2011.

        .. [3] Cheng J. et. al, "Theoretical Analysis and Practical Insights on EAP
        Estimation via a Unified HARDI Framework", MICCAI workshop on Computational
        Diffusion MRI, 2011.
        """

        self.bvals = gtab.bvals
        self.bvecs = gtab.bvecs
        self.gtab = gtab

    @multi_voxel_fit
    def fit(self, data):
        return AnalyticalFit(self, data)


class AnalyticalFit():

    def __init__(self, model, data):
        """ Calculates diffusion properties for a single voxel. This is an abstract class.

        Parameters
        ----------
        model : object,
            AnalyticalModel
        data : 1d ndarray,
            signal values
        """

        self.model = model
        self.data = data

    def l2estimation(self):
        """ Least square estimation with an $\ell_2$ regularisation of the $c_i$ coefficients.
        """

        pass

    def pdf(self):
        """ Applies the analytical FFT on $S$ to generate the diffusion propagator.
        """
        pass

    def odf(self, sphere):
        r""" Calculates the real analytical odf in terms of Spherical Harmonics.
        """

        pass


class ShoreModel(AnalyticalModel):

    def __init__(self, gtab):
        r""" Analytical and continuous modeling of the diffusion signal with respect to the SHORE
        basis [1,2]_.

        The main idea is to model the diffusion signal as a linear combination of continuous
        functions $\phi_i$,

        ..math::
            :nowrap:
                \begin{equation}
                    S(\mathbf{q})= \sum_{i=0}^I  c_{i} \phi_{i}(\mathbf{q}).
                \end{equation}

        where $\mathbf{q}$ is the wavector which corresponds to different gradient directions.

        From the $c_i$ coefficients, there exists an analytical formula to estimate the ODF.


        Parameters
        ----------
        gtab : GradientTable,
            Gradient directions and bvalues container class


        References
        ----------
        .. [1] Merlet S. et. al, "Continuous diffusion signal, EAP and ODF estimation via
        Compressive Sensing in diffusion MRI", Medical Image Analysis, 2013.


        .. [2] Cheng J. et. al, "Theoretical Analysis and Practical Insights on EAP
        Estimation via a Unified HARDI Framework", MICCAI workshop on Computational
        Diffusion MRI, 2011.




        Examples
        --------
        In this example where we provide the data, a gradient table
        and a reconstruction sphere, we model the diffusion signal with respect
        to the SHORE basis and compute the real and analytical ODF in terms of
        Spherical Harmonics.

        from dipy.data import get_data,get_sphere
        sphere = get_sphere('symmetric724')
        fimg, fbvals, fbvecs = get_data('ISBI_testing_2shells_table')
        bvals, bvecs = read_bvals_bvecs(fbvals, fbvecs)
        gtab = gradient_table(bvals[1:], bvecs[1:,:])
        from dipy.sims.voxel import SticksAndBall
        data, golden_directions = SticksAndBall(gtab, d=0.0015,
                                                S0=1, angles=[(0, 0), (90, 0)],
                                                fractions=[50, 50], snr=None)
        from dipy.reconst.canal import ShoreModel
        asm = ShoreModel(gtab)
        asmfit = asm.fit(data)
        radialOrder = 4
        zeta = 700
        Cshore, Sshore = asmfit.l2estimation(radialOrder=radialOrder, zeta=zeta, lambdaN=1e-8, lambdaL=1e-8)
        Csh = asmfit.odf()
        """

        self.bvals = gtab.bvals
        self.bvecs = gtab.bvecs
        self.gtab = gtab

    @multi_voxel_fit
    def fit(self, data):
        return ShoreFit(self, data)


class ShoreFit(AnalyticalFit):

    def __init__(self, model, data):
        """ Calculates diffusion properties for a single voxel

        Parameters
        ----------
        model : object,
            AnalyticalModel
        data : 1d ndarray,
            signal values
        """

        self.model = model
        self.data = data
        self.gtab = model.gtab
        self.Cshore = None

    def l2estimation(self, radialOrder=6, zeta=700, lambdaN=1e-8, lambdaL=1e-8):
        """ Least square estimation with an $\ell_2$ regularisation of the $c_i$ coefficients.

        Parameters
        ----------
        radialOrder : unsigned int,
            Radial Order
        zeta : unsigned int,
            scale factor
        lambdaN : float,
            radial regularisation constant
        lambdaL : float,
            angular regularisation constant
        """

        self.radialOrder = radialOrder
        self.zeta = zeta
        Lshore = L_SHORE(self.radialOrder)
        Nshore = N_SHORE(self.radialOrder)
        #Generate the SHORE basis
        M= self.model.cache_get('shore_matrix', key=self.gtab)
        if M is None:
            M = SHOREmatrix(self.radialOrder,  self.zeta, self.gtab)
            self.model.cache_set('shore_matrix', self.gtab, M)

        #Compute the signal coefficients in SHORE basis
        pseudoInv = np.dot(np.linalg.inv(np.dot(M.T, M) + lambdaN * Nshore + lambdaL * Lshore), M.T)
        self.Cshore = np.dot(pseudoInv, self.data)

        return self.Cshore 

    def pdf(self, gridsize, radius_max):
        """ Applies the analytical FFT on $S$ to generate the diffusion propagator.

        Parameters
        ----------
        gridsize : unsigned int
            dimension of the propagator grid
        radius_max : float
            maximal radius in which compute the propagator
        
        Returns
        -------
        Pr : ndarray
            the propagator in the 3D grid
        psi : ndarray
            shore propagator matrix $psi$ 

        """
        Pr = np.zeros((gridsize, gridsize, gridsize))
        # Create the grid in wich compute the pdf
        rgrid, rtab = create_rspace(gridsize, radius_max)
        psi= self.model.cache_get('shore_matrix_pdf', key=gridsize)
        if psi is None:
            psi = SHOREmatrix_pdf(self.radialOrder,  self.zeta, rtab)
            self.model.cache_set('shore_matrix_pdf', gridsize, psi)
        
        propagator = np.dot(psi, self.Cshore)
        # fill R-space
        for i in range(len(rgrid)):
            qx, qy, qz = rgrid[i]
            Pr[qx, qy, qz] += propagator[i]
        # normalize by the area of the propagator 
        Pr = Pr * (2 * radius_max / gridsize) ** 3
        return Pr, psi

    def pdf_iso(self, points):
        """ Diffusion propagator on a given shell.
        """
        
        psi = SHOREmatrix_pdf(self.radialOrder,  self.zeta, sphere)
        Pr = np.dot(psi, self.Cshore)

        return Pr
        
    def odf_sh(self):
        r""" Calculates the real analytical odf in terms of Spherical Harmonics.
        """

        # Number of Spherical Harmonics involved in the estimation
        J = (self.radialOrder + 1) * (self.radialOrder + 2) / 2

        # Compute the spherical Harmonic Coefficients
        Csh = np.zeros(J)
        counter = 0

        for n in range(self.radialOrder + 1):
            for l in range(0, n + 1, 2):
                for m in range(-l, l + 1):

                    j = int(l + m + (2 * np.array(range(0, l, 2)) + 1).sum())

                    Cnl = ((-1) ** (n - l / 2)) / (2.0 * (4.0 * np.pi ** 2 * self.zeta) ** (3.0 / 2.0)) * ((2.0 * (
                        4.0 * np.pi ** 2 * self.zeta) ** (3.0 / 2.0) * factorial(n - l)) / (gamma(n + 3.0 / 2.0))) ** (1.0 / 2.0)
                    Gnl = (gamma(l / 2 + 3.0 / 2.0) * gamma(3.0 / 2.0 + n)) / (gamma(
                        l + 3.0 / 2.0) * factorial(n - l)) * (1.0 / 2.0) ** (-l / 2 - 3.0 / 2.0)
                    Fnl = hyp2f1(-n + l, l / 2 + 3.0 / 2.0, l + 3.0 / 2.0, 2.0)

                    Csh[j] += self.Cshore[counter] * Cnl * Gnl * Fnl
                    counter += 1

        return Csh

    def odf(self, sphere):
        r""" Calculates the real analytical odf for a given discrete sphere.
        """
        upsilon= self.model.cache_get('shore_matrix_odf', key=sphere)
        if upsilon is None:
            upsilon = SHOREmatrix_odf(self.radialOrder,  self.zeta, sphere.vertices)
            self.model.cache_set('shore_matrix_odf', sphere, upsilon)
        
        odf = np.dot (upsilon , self.Cshore)
        return odf

    def rtop_signal(self):
        r""" Calculates the analytical return to origin probability from the signal. 
        """
        rtop = 0
        c = self.Cshore
        counter = 0
        for n in range(self.radialOrder + 1):
            for l in range(0, n + 1, 2):
                for m in range(-l, l + 1):
                    if l == 0:
                        rtop +=  c[counter] * (-1) ** n * \
                            ((16 * np.pi * self.zeta ** 1.5 * gamma(n + 1.5)) / (
                             factorial(n))) ** 0.5
                    counter += 1
        return rtop

    def rtop_pdf(self):
        r""" Calculates the analytical return to origin probability from the pdf. 
        """
        rtop = 0
        c = self.Cshore
        counter = 0
        for n in range(self.radialOrder + 1):
            for l in range(0, n + 1, 2):
                for m in range(-l, l + 1):
                    if l == 0:
                        rtop += c[counter] * (-1) ** n * \
                            ((4 * np.pi ** 2 * self.zeta ** 1.5 * factorial(n)) / (gamma(n + 1.5))) ** 0.5 * \
                            genlaguerre(n, 0.5)(0)
                    counter += 1
        return rtop

    def msd(self):
        r""" Calculates the analytical mean squared displacement 

        ..math::
            :nowrap:
                \begin{equation}
                    MSD:{DSI}=\int_{-\infty}^{\infty}\int_{-\infty}^{\infty}\int_{-\infty}^{\infty} P(\hat{\mathbf{r}}) \cdot \hat{\mathbf{r}}^{2} \ dr_x \ dr_y \ dr_z
                \end{equation}

        where $\hat{\mathbf{r}}$ is a point in the 3D Propagator space (see Wu et. al [1]_).

        References
        ----------
        .. [1] Wu Y. et. al, "Hybrid diffusion imaging", NeuroImage, vol 36,
        p. 617-629, 2007.

        """
        msd = 0
        c = self.Cshore
        counter = 0
        for n in range(self.radialOrder + 1):
            for l in range(0, n + 1, 2):
                for m in range(-l, l + 1):
                    if l == 0:
                        msd += c[counter]  * (-1) ** n *\
                            (9 * (gamma(n + 1.5)) / (8 * np.pi ** 6  *  self.zeta ** 3.5 * factorial(n))) ** 0.5 *\
                            hyp2f1(-n, 2.5, 1.5, 2)
                    counter += 1
        return msd


def SHOREmatrix(radialOrder, zeta, gtab):
    """Compute the SHORE matrix"

    Parameters
    ----------
    radialOrder : unsigned int,
        Radial Order
    zeta : unsigned int,
        scale factor
    gtab : GradientTable,
        Gradient directions and bvalues container class
    """

    qvals = np.sqrt(gtab.bvals)
    bvecs = gtab.bvecs

    qgradients = qvals[:, None] * bvecs

    r, theta, phi = cart2sphere(
        qgradients[:, 0], qgradients[:, 1], qgradients[:, 2])
    theta[np.isnan(theta)] = 0

    M = np.zeros(
        (r.shape[0], (radialOrder + 1) * ((radialOrder + 1) / 2) * (2 * radialOrder + 1)))

    counter = 0
    for n in range(radialOrder + 1):
        for l in range(0, n + 1, 2):
            for m in range(-l, l + 1):

                M[:, counter] = \
                    real_sph_harm(m, l, theta, phi) * \
                    genlaguerre(n - l, l + 0.5)(r ** 2 / float(zeta)) * \
                    np.exp(- r ** 2 / (2.0 * zeta)) * \
                    __kappa(zeta, n, l) * \
                    (r ** 2 / float(zeta)) ** (l / 2)

                counter += 1
    return M[:, 0:counter]


def __kappa(zeta, n, l):
    if n - l < 0:
        return np.sqrt((2 * 1) / (zeta ** 1.5 * gamma(n + 1.5)))
    else:
        return np.sqrt((2 * factorial(n - l)) / (zeta ** 1.5 * gamma(n + 1.5)))


def SHOREmatrix_pdf(radialOrder, zeta, rtab):
    """Compute the SHORE matrix"

    Parameters
    ----------
    radialOrder : unsigned int,
        Radial Order
    zeta : unsigned int,
        scale factor
    rtab : array, shape (N,3)
        r-space points in which calculates the pdf
    """

    r, theta, phi = cart2sphere(
        rtab[:, 0], rtab[:, 1], rtab[:, 2])
    theta[np.isnan(theta)] = 0

    psi = np.zeros(
        (r.shape[0], (radialOrder + 1) * ((radialOrder + 1) / 2) * (2 * radialOrder + 1)))
    counter = 0
    for n in range(radialOrder + 1):
        for l in range(0, n + 1, 2):
            for m in range(-l, l + 1):

                psi[:, counter] = real_sph_harm(m, l, theta, phi) * \
                    genlaguerre(n - l, l + 0.5)(4 * np.pi ** 2 * zeta * r ** 2 ) *\
                    np.exp(-2 * np.pi ** 2 * zeta * r ** 2) *\
                    __kappa_pdf(zeta, n, l) *\
                    (4 * np.pi ** 2 * zeta * r ** 2) ** (l / 2) * \
                    (-1) ** (n - l / 2)

                counter += 1
    return psi[:, 0:counter]


def __kappa_pdf(zeta, n, l):
    if n - l < 0:
        return np.sqrt((16 * np.pi ** 3 * zeta ** 1.5) / gamma(n + 1.5))
    else:
        return np.sqrt((16 * np.pi ** 3 * zeta ** 1.5 * factorial(n - l)) / gamma(n + 1.5))

def SHOREmatrix_odf(radialOrder, zeta, sphere_vertices):
    """Compute the SHORE matrix"

    Parameters
    ----------
    radialOrder : unsigned int,
        Radial Order
    zeta : unsigned int,
        scale factor
    sphere_vertices : array, shape (N,3)
        vertices of the odf sphere
    """

    r, theta, phi = cart2sphere(sphere_vertices[:, 0], sphere_vertices[:, 1], sphere_vertices[:, 2])
    theta[np.isnan(theta)] = 0
    counter = 0
    upsilon = np.zeros((len(sphere_vertices), (radialOrder + 1) * ((radialOrder + 1) / 2) * (2 * radialOrder + 1)))
    for n in range(radialOrder + 1):
        for l in range(0, n + 1, 2):
            for m in range(-l, l + 1):
                upsilon[:, counter] = (-1) ** (n - l / 2.0) * __kappa_odf(zeta,n,l) * \
                    hyp2f1(l - n, l / 2.0 + 1.5, l + 1.5, 2.0) * \
                    real_sph_harm(m, l, theta, phi)
                counter += 1

    return upsilon[:, 0:counter]

def __kappa_odf(zeta, n, l):
    if n - l < 0:
        return np.sqrt((gamma(l / 2.0 + 1.5) ** 2 * gamma(n + 1.5) * 2 ** (l + 3)) /
                    (16 * np.pi ** 3 * (zeta) ** 1.5  * gamma(l + 1.5) ** 2))
    else:
        return np.sqrt((gamma(l / 2.0 + 1.5) ** 2 * gamma(n + 1.5) * 2 ** (l + 3)) /
                    (16 * np.pi ** 3 * (zeta) ** 1.5 * factorial(n - l) * gamma(l + 1.5) ** 2))


def L_SHORE(radialOrder):
    "Returns the angular regularisation matrix for SHORE basis"
    diagL = np.zeros(
        (radialOrder + 1) * ((radialOrder + 1) / 2) * (2 * radialOrder + 1))
    counter = 0
    for n in range(radialOrder + 1):
        for l in range(0, n + 1, 2):
            for m in range(-l, l + 1):
                # print(counter)
                # print "(n,l,m) = (%d,%d,%d)" % (n,l,m)
                # print(counter)
                diagL[counter] = (l * (l + 1)) ** 2
                counter += 1

    return np.diag(diagL[0:counter])


def N_SHORE(radialOrder):
    "Returns the angular regularisation matrix for SHORE basis"
    diagN = np.zeros(
        (radialOrder + 1) * ((radialOrder + 1) / 2) * (2 * radialOrder + 1))
    counter = 0
    for n in range(radialOrder + 1):
        for l in range(0, n + 1, 2):
            for m in range(-l, l + 1):
                # print(counter)
                # print "(n,l,m) = (%d,%d,%d)" % (n,l,m)
                # print(counter)
                diagN[counter] = (n * (n + 1)) ** 2
                counter += 1

    return np.diag(diagN[0:counter])


def create_rspace(gridsize, radius_max):
    """ create the r-space table, that contains the points in which 
        compute the pdf.

    Parameters
    ----------
    gridsize : unsigned int
        dimension of the propagator grid
    radius_max : float
        maximal radius in which compute the propagator

    Returns
    -------
    vecs : array, shape (N,3)
        positions of the pdf points in a 3D matrix

    tab : array, shape (N,3)
        r-space points in which calculates the pdf
    """

    radius = gridsize // 2
    vecs = []
    for i in range(-radius, radius + 1):
        for j in range(-radius, radius + 1):
            for k in range(-radius, radius + 1):
                vecs.append([i, j, k])

    vecs = np.array(vecs, dtype=np.float32)
    tab = vecs / float(radius)
    tab = tab * radius_max
    vecs = vecs + radius

    return vecs, tab
