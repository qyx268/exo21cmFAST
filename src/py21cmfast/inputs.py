"""
Input parameter classes.

There are four input parameter/option classes, not all of which are required for any
given function. They are :class:`UserParams`, :class:`CosmoParams`, :class:`AstroParams`
and :class:`FlagOptions`. Each of them defines a number of variables, and all of these
have default values, to minimize the burden on the user. These defaults are accessed via
the ``_defaults_`` class attribute of each class. The available parameters for each are
listed in the documentation for each class below.

Along with these, the module exposes ``global_params``, a singleton object of type
:class:`GlobalParams`, which is a simple class providing read/write access to a number of parameters
used throughout the computation which are very rarely varied.
"""
import logging
from os import path

from astropy.cosmology import Planck15

from ._utils import StructInstanceWrapper
from ._utils import StructWithDefaults
from .c_21cmfast import ffi
from .c_21cmfast import lib

logger = logging.getLogger("21cmFAST")


class GlobalParams(StructInstanceWrapper):
    """
    Global parameters for 21cmFAST.

    This is a thin wrapper over an allocated C struct, containing parameter values
    which are used throughout various computations within 21cmFAST. It is a singleton;
    that is, a single python (and C) object exists, and no others should be created.
    This object is not "passed around", rather its values are accessed throughout the
    code.

    Parameters in this struct are considered to be options that should usually not have
    to be modified, and if so, typically once in any given script or session.

    Values can be set in the normal way, eg.:

    >>> global_params.ALPHA_UVB = 5.5

    Attributes
    ----------
    ALPHA_UVB : float
        Power law index of the UVB during the EoR.  This is only used if `INHOMO_RECO` is
        True (in :class:`FlagOptions`), in order to compute the local mean free path
        inside the cosmic HII regions.
    EVOLVE_DENSITY_LINEARLY : bool
        Whether to evolve the density field with linear theory (instead of 1LPT or Zel'Dovich).
        If choosing this option, make sure that your cell size is
        in the linear regime at the redshift of interest. Otherwise, make sure you resolve
        small enough scales, roughly we find BOX_LEN/DIM should be < 1Mpc
    SMOOTH_EVOLVED_DENSITY_FIELD : bool
        If True, the zeldovich-approximation density field is additionally smoothed
        (aside from the implicit boxcar smoothing performed when re-binning the ICs from
        DIM to HII_DIM) with a Gaussian filter of width ``R_smooth_density*BOX_LEN/HII_DIM``.
        The implicit boxcar smoothing in ``perturb_field()`` bins the density field on
        scale DIM/HII_DIM, similar to what Lagrangian codes do when constructing Eulerian
        grids. In other words, the density field is quantized into ``(DIM/HII_DIM)^3`` values.
        If your usage requires smooth density fields, it is recommended to set this to True.
        This also decreases the shot noise present in all grid based codes, though it
        overcompensates by an effective loss in resolution. **Added in 1.1.0**.
    R_smooth_density : float
        Determines the smoothing length to use if `SMOOTH_EVOLVED_DENSITY_FIELD` is True.
    SECOND_ORDER_LPT_CORRECTIONS : bool
        Use second-order Lagrangian perturbation theory (2LPT).
        Set this to True if the density field or the halo positions are extrapolated to
        low redshifts. The current implementation is very naive and adds a factor ~6 to
        the memory requirements. Reference: Scoccimarro R., 1998, MNRAS, 299, 1097-1118
        Appendix D.
    HII_ROUND_ERR : float
        Rounding error on the ionization fraction. If the mean xHI is greater than
        ``1 - HII_ROUND_ERR``, then finding HII bubbles is skipped, and a homogeneous
        xHI field of ones is returned. Added in  v1.1.0.
    FIND_BUBBLE_ALGORITHM : int, {1,2}
        Choose which algorithm used to find HII bubbles. Options are: (1) Mesinger & Furlanetto 2007
        method of overlapping spheres: paint an ionized sphere with radius R, centered on pixel
        where R is filter radius. This method, while somewhat more accurate, is slower than (2),
        especially in mostly ionized universes, so only use for lower resolution boxes
        (HII_DIM<~400). (2) Center pixel only method (Zahn et al. 2007). This is faster.
    N_POISSON : int
        If not using the halo field to generate HII regions, we provide the option of
        including Poisson scatter in the number of sources obtained through the conditional
        collapse fraction (which only gives the *mean* collapse fraction on a particular
        scale. If the predicted mean collapse fraction is less than  `N_POISSON * M_MIN`,
        then Poisson scatter is added to mimic discrete halos on the subgrid scale (see
        Zahn+2010).Use a negative number to turn it off.

        .. note:: If you are interested in snapshots of the same realization at several
                  redshifts,it is recommended to turn off this feature, as halos can
                  stochastically "pop in and out of" existence from one redshift to the next.

    T_USE_VELOCITIES : bool
        Whether to use velocity corrections in 21-cm fields

        .. note:: The approximation used to include peculiar velocity effects works
                  only in the linear regime, so be careful using this (see Mesinger+2010)

    MAX_DVDR : float
        Maximum velocity gradient along the line of sight in units of the hubble parameter at z.
        This is only used in computing the 21cm fields.

        .. note:: Setting this too high can add spurious 21cm power in the early stages,
                  due to the 1-e^-tau ~ tau approximation (see Mesinger's 21cm intro paper and mao+2011).
                  However, this is still a good approximation at the <~10% level.

    VELOCITY_COMPONENT : int
        Component of the velocity to be used in 21-cm temperature maps (1=x, 2=y, 3=z)
    DELTA_R_HII_FACTOR : float
        Factor by which to scroll through filter radius for bubbles
    HII_FILTER : int, {0, 1, 2}
        Filter for the Halo or density field used to generate ionization field:
        0. real space top hat filter
        1. k-space top hat filter
        2. gaussian filter
    INITIAL_REDSHIFT : float
        Used to perturb field
    CRIT_DENS_TRANSITION : float
        A transition value for the interpolation tables for calculating the number of ionising
        photons produced given the input parameters. Log sampling is desired, however the numerical
        accuracy near the critical density for collapse (i.e. 1.69) broke down. Therefore, below the
        value for `CRIT_DENS_TRANSITION` log sampling of the density values is used, whereas above
        this value linear sampling is used.
    MIN_DENSITY_LOW_LIMIT : float
        Required for using the interpolation tables for the number of ionising photons. This is a
        lower limit for the density values that is slightly larger than -1. Defined as a density
        contrast.
    RecombPhotonCons : int
        Whether or not to use the recombination term when calculating the filling factor for
        performing the photon non-conservation correction.
    PhotonConsStart : float
        A starting value for the neutral fraction where the photon non-conservation correction is
        performed exactly. Any value larger than this the photon non-conservation correction is not
        performed (i.e. the algorithm is perfectly photon conserving).
    PhotonConsEnd : float
        An end-point for where the photon non-conservation correction is performed exactly. This is
        required to remove undesired numerical artifacts in the resultant neutral fraction histories.
    PhotonConsAsymptoteTo : float
        Beyond `PhotonConsEnd` the photon non-conservation correction is extrapolated to yield
        smooth reionisation histories. This sets the lowest neutral fraction value that the photon
        non-conservation correction will be applied to.
    HEAT_FILTER : int
        Filter used for smoothing the linear density field to obtain the collapsed fraction:
            0: real space top hat filter
            1: sharp k-space filter
            2: gaussian filter
    CLUMPING_FACTOR : float
        Sub grid scale. If you want to run-down from a very high redshift (>50), you should
        set this to one.
    Z_HEAT_MAX : float
        Maximum redshift used in the Tk and x_e evolution equations.
        Temperature and x_e are assumed to be homogeneous at higher redshifts.
        Lower values will increase performance.
    R_XLy_MAX : float
        Maximum radius of influence for computing X-ray and Lya pumping in cMpc. This
        should be larger than the mean free path of the relevant photons.
    NUM_FILTER_STEPS_FOR_Ts : int
        Number of spherical annuli used to compute df_coll/dz' in the simulation box.
        The spherical annuli are evenly spaced in logR, ranging from the cell size to the box
        size. :func:`~wrapper.spin_temp` will create this many boxes of size `HII_DIM`,
        so be wary of memory usage if values are high.
    ZPRIME_STEP_FACTOR : float
        Logarithmic redshift step-size used in the z' integral.  Logarithmic dz.
        Decreasing (closer to unity) increases total simulation time for lightcones,
        and for Ts calculations.
    TK_at_Z_HEAT_MAX : float
        If positive, then overwrite default boundary conditions for the evolution
        equations with this value. The default is to use the value obtained from RECFAST.
        See also `XION_at_Z_HEAT_MAX`.
    XION_at_Z_HEAT_MAX : float
        If positive, then overwrite default boundary conditions for the evolution
        equations with this value. The default is to use the value obtained from RECFAST.
        See also `TK_at_Z_HEAT_MAX`.
    Pop : int
        Stellar Population responsible for early heating (2 or 3)
    Pop2_ion : float
        Number of ionizing photons per baryon for population 2 stellar species.
    Pop3_ion : float
        Number of ionizing photons per baryon for population 3 stellar species.
    NU_X_BAND_MAX : float
        This is the upper limit of the soft X-ray band (0.5 - 2 keV) used for normalising
        the X-ray SED to observational limits set by the X-ray luminosity. Used for performing
        the heating rate integrals.
    NU_X_MAX : float
        An upper limit (must be set beyond `NU_X_BAND_MAX`) for performing the rate integrals.
        Given the X-ray SED is modelled as a power-law, this removes the potential of divergent
        behaviour for the heating rates. Chosen purely for numerical convenience though it is
        motivated by the fact that observed X-ray SEDs apprear to turn-over around 10-100 keV
        (Lehmer et al. 2013, 2015)
    NBINS_LF : int
        Number of bins for the luminosity function calculation.
    P_CUTOFF : bool
        Turn on Warm-Dark-matter power suppression.
    M_WDM : float
        Mass of WDM particle in keV. Ignored if `P_CUTOFF` is False.
    g_x : float
        Degrees of freedom of WDM particles; 1.5 for fermions.
    OMn : float
        Relative density of neutrinos in the universe.
    OMk : float
        Relative density of curvature.
    OMr : float
        Relative density of radiation.
    OMtot : float
        Fractional density of the universe with respect to critical density. Set to
        unity for a flat universe.
    Y_He : float
        Helium fraction.
    wl : float
        Dark energy equation of state parameter (wl = -1 for vacuum )
    SHETH_b : float
        Sheth-Tormen parameter for ellipsoidal collapse (for HMF).

        .. note:: The best fit b and c ST params for these 3D realisations have a redshift,
                  and a ``DELTA_R_FACTOR`` dependence, as shown
                  in Mesinger+. For converged mass functions at z~5-10, set `DELTA_R_FACTOR=1.1`
                  and `SHETH_b=0.15` and `SHETH_c~0.05`.

                  For most purposes, a larger step size is quite sufficient and provides an
                  excellent match to N-body and smoother mass functions, though the b and c
                  parameters should be changed to make up for some "stepping-over" massive
                  collapsed halos (see Mesinger, Perna, Haiman (2005) and Mesinger et al.,
                  in preparation).

                  For example, at z~7-10, one can set `DELTA_R_FACTOR=1.3` and `SHETH_b=0.15`
                   and `SHETH_c=0.25`, to increase the speed of the halo finder.
    SHETH_c : float
        Sheth-Tormen parameter for ellipsoidal collapse (for HMF). See notes for `SHETH_b`.
    Zreion_HeII : float
        Redshift of helium reionization, currently only used for tau_e
    FILTER : int, {0, 1}
        Filter to use for smoothing.
        0. tophat
        1. gaussian
    external_table_path : str
        The system path to find external tables for calculation speedups. DO NOT MODIFY.
    """

    def __init__(self, wrapped, ffi):
        super().__init__(wrapped, ffi)

        EXTERNALTABLES = ffi.new(
            "char[]", path.join(path.expanduser("~"), ".21cmfast").encode()
        )
        self.external_table_path = EXTERNALTABLES


global_params = GlobalParams(lib.global_params, ffi)


class CosmoParams(StructWithDefaults):
    """
    Cosmological parameters (with defaults) which translates to a C struct.

    To see default values for each parameter, use ``CosmoParams._defaults_``.
    All parameters passed in the constructor are also saved as instance attributes which should
    be considered read-only. This is true of all input-parameter classes.

    Parameters
    ----------
    SIGMA_8 : float, optional
        RMS mass variance (power spectrum normalisation).
    hlittle : float, optional
        The hubble parameter, H_0/100.
    OMm : float, optional
        Omega matter.
    OMb : float, optional
        Omega baryon, the baryon component.
    POWER_INDEX : float, optional
        Spectral index of the power spectrum.
    """

    _ffi = ffi

    _defaults_ = {
        "SIGMA_8": 0.82,
        "hlittle": Planck15.h,
        "OMm": Planck15.Om0,
        "OMb": Planck15.Ob0,
        "POWER_INDEX": 0.97,
    }

    @property
    def OMl(self):
        """Omega lambda, dark energy density."""
        return 1 - self.OMm

    @property
    def cosmo(self):
        """Return an astropy cosmology object for this cosmology."""
        return Planck15.clone(H0=self.hlittle * 100, Om0=self.OMm, Ob0=self.OMb)


class UserParams(StructWithDefaults):
    """
    Structure containing user parameters (with defaults).

    To see default values for each parameter, use ``UserParams._defaults_``.
    All parameters passed in the constructor are also saved as instance attributes which should
    be considered read-only. This is true of all input-parameter classes.

    Parameters
    ----------
    HII_DIM : int, optional
        Number of cells for the low-res box. Default 50.
    DIM : int,optional
        Number of cells for the high-res box (sampling ICs) along a principal axis. To avoid
        sampling issues, DIM should be at least 3 or 4 times HII_DIM, and an integer multiple.
        By default, it is set to 4*HII_DIM.
    BOX_LEN : float, optional
        Length of the box, in Mpc. Default 150.
    HMF: int or str, optional
        Determines which halo mass function to be used for the normalisation of the
        collapsed fraction (default Sheth-Tormen). If string should be one of the
        following codes:
        0: PS (Press-Schechter)
        1: ST (Sheth-Tormen)
        2: Watson (Watson FOF)
        3: Watson-z (Watson FOF-z)
    USE_RELATIVE_VELOCITIES: int, optional
        Flag to decide whether to use relative velocities, default True.
        If True, POWER_SPECTRUM is automatically set to 5. Default False.
    POWER_SPECTRUM: int or str, optional
        Determines which power spectrum to use, default EH (unless `USE_RELATIVE_VELOCITIES`
        is True). If string, use the following codes:
        0: EH
        1: BBKS
        2: EFSTATHIOU
        3: PEEBLES
        4: WHITE
        5: CLASS (single output)
    """

    _ffi = ffi

    _defaults_ = {
        "BOX_LEN": 150.0,
        "DIM": None,
        "HII_DIM": 50,
        "USE_FFTW_WISDOM": False,
        "HMF": 1,
        "USE_RELATIVE_VELOCITIES": False,
        "POWER_SPECTRUM": 0,
    }

    _hmf_models = ["PS", "ST", "WATSON", "WATSON-Z"]
    _power_models = ["EH", "BBKS", "EFSTATHIOU", "PEEBLES", "WHITE", "CLASS"]

    @property
    def DIM(self):
        """Number of cells for the high-res box (sampling ICs) along a principal axis."""
        return self._DIM or 4 * self.HII_DIM

    @property
    def tot_fft_num_pixels(self):
        """Total number of pixels in the high-res box."""
        return self.DIM ** 3

    @property
    def HII_tot_num_pixels(self):
        """Total number of pixels in the low-res box."""
        return self.HII_DIM ** 3

    @property
    def POWER_SPECTRUM(self):
        """
        The power spectrum generator to use, as an integer.

        See :func:`power_spectrum_model` for a string representation.
        """
        if self.USE_RELATIVE_VELOCITIES:
            if self._POWER_SPECTRUM != 5 or (
                isinstance(self._POWER_SPECTRUM, str)
                and self._POWER_SPECTRUM.upper() != "CLASS"
            ):
                logger.warning(
                    "Automatically setting POWER_SPECTRUM to 5 (CLASS) as you are using "
                    "relative velocities"
                )
            return 5
        else:
            if isinstance(self._POWER_SPECTRUM, str):
                val = self._power_models.index(self._POWER_SPECTRUM.upper())
            else:
                val = self._POWER_SPECTRUM

            if not 0 <= val < len(self._power_models):
                raise ValueError(
                    "Power spectrum must be between 0 and {}".format(
                        len(self._power_models) - 1
                    )
                )

            return val

    @property
    def HMF(self):
        """The HMF to use (an int, mapping to a given form).

        See hmf_model for a string representation.
        """
        if isinstance(self._HMF, str):
            val = self._hmf_models.index(self._HMF.upper())
        else:
            val = self._HMF

        try:
            val = int(val)
        except (ValueError, TypeError):
            raise ValueError("Invalid value for HMF")

        if not 0 <= val < len(self._hmf_models):
            raise ValueError(
                "HMF must be an int between 0 and {}".format(len(self._hmf_models) - 1)
            )

        return val

    @property
    def hmf_model(self):
        """String representation of the HMF model used."""
        return self._hmf_models[self.HMF]

    @property
    def power_spectrum_model(self):
        """String representation of the power spectrum model used."""
        return self._power_models[self.POWER_SPECTRUM]


class FlagOptions(StructWithDefaults):
    """
    Flag-style options for the ionization routines.

    To see default values for each parameter, use ``FlagOptions._defaults_``.
    All parameters passed in the constructor are also saved as instance attributes
    which should be considered read-only. This is true of all input-parameter classes.

    Note that all flags are set to False by default, giving the simplest "vanilla"
    version of 21cmFAST.

    Parameters
    ----------
    USE_MASS_DEPENDENT_ZETA : bool, optional
        Set to True if using new parameterization. Setting to True will automatically
        set `M_MIN_in_Mass` to True.
    SUBCELL_RSDS : bool, optional
        Add sub-cell redshift-space-distortions (cf Sec 2.2 of Greig+2018).
        Will only be effective if `USE_TS_FLUCT` is True.
    INHOMO_RECO : bool, optional
        Whether to perform inhomogeneous recombinations. Increases the computation
        time.
    USE_TS_FLUCT : bool, optional
        Whether to perform IGM spin temperature fluctuations (i.e. X-ray heating).
        Dramatically increases the computation time.
    M_MIN_in_Mass : bool, optional
        Whether the minimum halo mass (for ionization) is defined by
        mass or virial temperature. Automatically True if `USE_MASS_DEPENDENT_ZETA`
        is True.
    PHOTON_CONS : bool, optional
        Whether to perform a small correction to account for the inherent
        photon non-conservation.
    """

    _ffi = ffi

    _defaults_ = {
        "USE_MASS_DEPENDENT_ZETA": False,
        "SUBCELL_RSD": False,
        "INHOMO_RECO": False,
        "USE_TS_FLUCT": False,
        "M_MIN_in_Mass": False,
        "PHOTON_CONS": False,
    }

    @property
    def M_MIN_in_Mass(self):
        """Whether minimum halo mass is defined in mass or virial temperature."""
        if self.USE_MASS_DEPENDENT_ZETA:
            return True

        else:
            return self._M_MIN_in_Mass


class AstroParams(StructWithDefaults):
    """
    Astrophysical parameters.

    To see default values for each parameter, use ``AstroParams._defaults_``.
    All parameters passed in the constructor are also saved as instance attributes which should
    be considered read-only. This is true of all input-parameter classes.

    Parameters
    ----------
    INHOMO_RECO : bool, optional
        Whether inhomogeneous recombinations are being calculated. This is not a part of the
        astro parameters structure, but is required by this class to set some default behaviour.
    HII_EFF_FACTOR : float, optional
        The ionizing efficiency of high-z galaxies (zeta, from Eq. 2 of Greig+2015).
        Higher values tend to speed up reionization.
    F_STAR10 : float, optional
        The fraction of galactic gas in stars for 10^10 solar mass haloes.
        Only used in the "new" parameterization,
        i.e. when `USE_MASS_DEPENDENT_ZETA` is set to True (in :class:`FlagOptions`).
        If so, this is used along with `F_ESC10` to determine `HII_EFF_FACTOR` (which
        is then unused). See Eq. 11 of Greig+2018 and Sec 2.1 of Park+2018.
        Given in log10 units.
    ALPHA_STAR : float, optional
        Power-law index of fraction of galactic gas in stars as a function of halo mass.
        See Sec 2.1 of Park+2018.
    F_ESC10 : float, optional
        The "escape fraction", i.e. the fraction of ionizing photons escaping into the
        IGM, for 10^10 solar mass haloes. Only used in the "new" parameterization,
        i.e. when `USE_MASS_DEPENDENT_ZETA` is set to True (in :class:`FlagOptions`).
        If so, this is used along with `F_STAR10` to determine `HII_EFF_FACTOR` (which
        is then unused). See Eq. 11 of Greig+2018 and Sec 2.1 of Park+2018.
    ALPHA_ESC : float, optional
        Power-law index of escape fraction as a function of halo mass. See Sec 2.1 of
        Park+2018.
    M_TURN : float, optional
        Turnover mass (in log10 solar mass units) for quenching of star formation in
        halos, due to SNe or photo-heating feedback, or inefficient gas accretion. Only
        used if `USE_MASS_DEPENDENT_ZETA` is set to True in :class:`FlagOptions`.
        See Sec 2.1 of Park+2018.
    R_BUBBLE_MAX : float, optional
        Mean free path in Mpc of ionizing photons within ionizing regions (Sec. 2.1.2 of
        Greig+2015). Default is 50 if `INHOMO_RECO` is True, or 15.0 if not.
    ION_Tvir_MIN : float, optional
        Minimum virial temperature of star-forming haloes (Sec 2.1.3 of Greig+2015).
        Given in log10 units.
    L_X : float, optional
        The specific X-ray luminosity per unit star formation escaping host galaxies.
        Cf. Eq. 6 of Greig+2018. Given in log10 units.
    NU_X_THRESH : float, optional
        X-ray energy threshold for self-absorption by host galaxies (in eV). Also called
        E_0 (cf. Sec 4.1 of Greig+2018). Typical range is (100, 1500).
    X_RAY_SPEC_INDEX : float, optional
        X-ray spectral energy index (cf. Sec 4.1 of Greig+2018). Typical range is
        (-1, 3).
    X_RAY_Tvir_MIN : float, optional
        Minimum halo virial temperature in which X-rays are produced. Given in log10
        units. Default is `ION_Tvir_MIN`.
    t_STAR : float, optional
        Fractional characteristic time-scale (fraction of hubble time) defining the
        star-formation rate of galaxies. Only used if `USE_MASS_DEPENDENT_ZETA` is set
        to True in :class:`FlagOptions`. See Sec 2.1, Eq. 3 of Park+2018.
    N_RSD_STEPS : int, optional
        Number of steps used in redshift-space-distortion algorithm. NOT A PHYSICAL
        PARAMETER.
    """

    _ffi = ffi

    _defaults_ = {
        "HII_EFF_FACTOR": 30.0,
        "F_STAR10": -1.3,
        "ALPHA_STAR": 0.5,
        "F_ESC10": -1.0,
        "ALPHA_ESC": -0.5,
        "M_TURN": 8.7,
        "R_BUBBLE_MAX": None,
        "ION_Tvir_MIN": 4.69897,
        "L_X": 40.0,
        "NU_X_THRESH": 500.0,
        "X_RAY_SPEC_INDEX": 1.0,
        "X_RAY_Tvir_MIN": None,
        "t_STAR": 0.5,
        "N_RSD_STEPS": 20,
    }

    def __init__(
        self, *args, INHOMO_RECO=FlagOptions._defaults_["INHOMO_RECO"], **kwargs
    ):
        # TODO: should try to get inhomo_reco out of here... just needed for default of
        #  R_BUBBLE_MAX.
        self.INHOMO_RECO = INHOMO_RECO
        super().__init__(*args, **kwargs)

    def convert(self, key, val):
        """Convert a given attribute before saving it the instance."""
        if key in [
            "F_STAR10",
            "F_ESC10",
            "M_TURN",
            "ION_Tvir_MIN",
            "L_X",
            "X_RAY_Tvir_MIN",
        ]:
            return 10 ** val
        else:
            return val

    @property
    def R_BUBBLE_MAX(self):
        """Maximum radius of bubbles to be searched. Set dynamically."""
        if not self._R_BUBBLE_MAX:
            return 50.0 if self.INHOMO_RECO else 15.0
        else:
            if self.INHOMO_RECO and self._R_BUBBLE_MAX != 50:
                logger.warning(
                    "You are setting R_BUBBLE_MAX != 50 when INHOMO_RECO=True. "
                    "This is non-standard (but allowed), and usually occurs upon manual "
                    "update of INHOMO_RECO"
                )
            return self._R_BUBBLE_MAX

    @property
    def X_RAY_Tvir_MIN(self):
        """Minimum virial temperature of X-ray emitting sources (unlogged and set dynamically)."""
        return self._X_RAY_Tvir_MIN if self._X_RAY_Tvir_MIN else self.ION_Tvir_MIN