""" some comparison functions
"""
import numpy
from automol.zmatrix._core import var_ as _var_
from automol.zmatrix._core import values as _values
from automol.zmatrix._core import distance_names as _distance_names
from automol.zmatrix._core import angle_names as _angle_names


def almost_equal(zma1, zma2, rtol=2e-5):
    """ are these z-matrices numerically equal?
    """
    ret = False
    if _var_(zma1) == _var_(zma2):
        val_dct1 = _values(zma1)
        val_dct2 = _values(zma2)
        dist_names = _distance_names(zma1)
        dist_vals1 = tuple(map(val_dct1.__getitem__, dist_names))
        dist_vals2 = tuple(map(val_dct2.__getitem__, dist_names))
        if numpy.allclose(dist_vals1, dist_vals2, rtol=rtol):
            ang_names = _angle_names(zma1)
            ang_vals1 = tuple(map(val_dct1.__getitem__, ang_names))
            ang_vals2 = tuple(map(val_dct2.__getitem__, ang_names))
            for shift in (0., numpy.pi/10.):
                ang_vals1 = numpy.mod(numpy.add(ang_vals1, shift), 2*numpy.pi)
                ang_vals2 = numpy.mod(numpy.add(ang_vals2, shift), 2*numpy.pi)
                if numpy.allclose(ang_vals1, ang_vals2, rtol=rtol):
                    ret = True
                    break
    return ret
