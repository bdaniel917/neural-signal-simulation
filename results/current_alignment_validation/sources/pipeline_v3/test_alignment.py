"""Meaningful checks of the independent interpolation sensitivity diagnostic."""
import unittest
import numpy as np
from alignment_checks import sinc_interpolate, check_trace


class InterpolationDiagnostic(unittest.TestCase):
    def test_fractional_queries_against_analytic_signal(self):
        time=np.arange(8000)/1000
        power=lambda t:.02*(1+.25*np.cos(2*np.pi*5*t))**2
        query=np.arange(200,600)/100-.007063
        reconstructed=sinc_interpolate(time,power(time),query,128)
        np.testing.assert_allclose(reconstructed,power(query),atol=1e-7,rtol=0)

    def test_exact_samples_and_insufficient_support(self):
        time=np.arange(8000)/1000;values=np.sin(time)
        np.testing.assert_allclose(sinc_interpolate(time,values,time[1000:1100],64),values[1000:1100],atol=1e-12,rtol=0)
        with self.assertRaises(ValueError):sinc_interpolate(time,values,np.array([.01]),64)

    def test_diagnostic_exposes_coarse_grid_error(self):
        time=np.arange(8000)/1000
        dense=np.column_stack((time,np.zeros(len(time)),.02*(1+.25*np.cos(2*np.pi*5*time))**2))
        metrics,_,_=check_trace(dense,np.arange(200,600)/100-.007063)
        self.assertGreater(metrics['fractional_query_samples'],0)
        self.assertLess(metrics['held_out_half_rate_nrmse'],1e-6)
        self.assertLess(metrics['cubic_vs_sinc128_nrmse'],1e-6)


if __name__=='__main__':unittest.main()
