import pytest
import numpy as np
from numpy.testing import assert_almost_equal
from astropy.utils.data import get_pkg_data_filename
from ..lightcurve import (LightCurve, KeplerCBVCorrector, KeplerLightCurveFile,
                          SFFCorrector, KeplerLightCurve)

# 8th Quarter of Tabby's star
TABBY_Q8 = ("https://archive.stsci.edu/missions/kepler/lightcurves"
            "/0084/008462852/kplr008462852-2011073133259_llc.fits")


def test_kepler_cbv_fit():
    # comparing that the two methods to do cbv fit are the nearly the same
    cbv = KeplerCBVCorrector(TABBY_Q8)
    cbv_lc = cbv.correct()
    assert_almost_equal(cbv.coeffs, [0.08534423, 0.10814261], decimal=3)
    lcf = KeplerLightCurveFile(TABBY_Q8)
    cbv_lcf = lcf.compute_cotrended_lightcurve()
    assert_almost_equal(cbv_lc.flux, cbv_lcf.flux)


def test_KeplerLightCurve():
    lcf = KeplerLightCurveFile(TABBY_Q8)
    kplc = lcf.get_lightcurve('SAP_FLUX')

    assert kplc.channel == lcf.channel
    assert kplc.campaign is None
    assert kplc.quarter == lcf.quarter
    assert kplc.mission == 'Kepler'


@pytest.mark.parametrize("quality_bitmask,answer", [('hardest', 2661),
    ('hard', 2706), ('default', 2917), (None, 3279),
    (1, 3279), (100, 3252), (2096639, 2661)])
def test_bitmasking(quality_bitmask, answer):
    '''Test whether the bitmasking behaves like it should'''
    lcf = KeplerLightCurveFile(TABBY_Q8, quality_bitmask=quality_bitmask)
    flux = lcf.get_lightcurve('SAP_FLUX').flux
    assert len(flux) == answer


def test_lightcurve_fold():
    """Test the ``LightCurve.fold()`` method."""
    lc = LightCurve(time=[1, 2, 3], flux=[1, 1, 1])
    assert_almost_equal(lc.fold(period=1).time[0], 0)
    assert_almost_equal(lc.fold(period=1, phase=-0.1).time[0], 0.1)


def test_cdpp():
    """Test the basics of the CDPP noise metric."""
    # A flat lightcurve should have a CDPP close to zero
    assert_almost_equal(LightCurve(np.arange(200), np.ones(200)).cdpp(), 0)
    # An artificial lightcurve with sigma=100ppm should have cdpp=100ppm
    lc = LightCurve(np.arange(10000), np.random.normal(loc=1, scale=100e-6, size=10000))
    assert_almost_equal(lc.cdpp(transit_duration=1), 100, decimal=-0.5)


def test_cdpp_tabby():
    """Compare the cdpp noise metric against the pipeline value."""
    lcf = KeplerLightCurveFile(TABBY_Q8)
    # Tabby's star shows dips after cadence 1000 which increase the cdpp
    lc = LightCurve(lcf.PDCSAP_FLUX.time[:1000], lcf.PDCSAP_FLUX.flux[:1000])
    assert(np.abs(lc.cdpp() - lcf.header(ext=1)['CDPP6_0']) < 30)


def test_lightcurve_plot():
    """Sanity check to verify that lightcurve plotting works"""
    lcf = KeplerLightCurveFile(TABBY_Q8)
    lcf.plot()
    lcf.SAP_FLUX.plot()


def test_sff_corrector():
    """Does our code agree with the example presented in Vanderburg
    and Jhonson (2014)?"""
    # The following csv file, provided by Vanderburg and Jhonson
    # at https://www.cfa.harvard.edu/~avanderb/k2/ep60021426.html,
    # contains the results of applying SFF to EPIC 60021426.
    fn = get_pkg_data_filename('./data/ep60021426alldiagnostics.csv')
    data = np.genfromtxt(fn, delimiter=',', skip_header=1)
    mask = data[:, -2] == 0 # indicates whether the thrusters were on or off
    time = data[:, 0][mask]
    raw_flux = data[:, 1][mask]
    corrected_flux = data[:, 2][mask]
    centroid_col = data[:, 3][mask]
    centroid_row = data[:, 4][mask]
    arclength = data[:, 5][mask]
    correction = data[:, 6][mask]

    sff = SFFCorrector()
    corrected_lc = sff.correct(time=time, flux=raw_flux,
                               centroid_col=centroid_col,
                               centroid_row=centroid_row,
                               niters=1)
    # the factor self.bspline(time-time[0]) accounts for
    # the long term trend which is divided out in order to get a "flat"
    # lightcurve.
    assert_almost_equal(corrected_lc.flux*sff.bspline(time-time[0]),
                        corrected_flux, decimal=3)
    assert_equal(time, corrected_lc.time)
    # the factor of 4 below accounts for the conversion
    # between pixel units to arcseconds
    # the factor of 0.136 accounts for the fact that
    # we are using the preprocessed (outlier-removed) centroids
    # rather than the full set of centroids
    assert_almost_equal(4*sff.s + 0.136, arclength, decimal=2)
    assert_almost_equal(sff.interp(sff.s), correction, decimal=3)

    # test using KeplerLightCurve interface
    klc = KeplerLightCurve(time=time, flux=raw_flux, centroid_col=centroid_col,
                           centroid_row=centroid_row)
    klc = klc.correct(niters=1)
    sff = klc.corrector

    assert_almost_equal(klc.flux*sff.bspline(time-time[0]),
                        corrected_flux, decimal=3)
    assert_almost_equal(4*sff.s + 0.136, arclength, decimal=2)
    assert_almost_equal(sff.interp(sff.s), correction, decimal=3)
    assert_equal(time, klc.time)


