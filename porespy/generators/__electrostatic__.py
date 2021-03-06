import numpy as np
from edt import edt
import porespy as ps
from porespy import settings
import scipy.ndimage as spim
tqdm = ps.tools.get_tqdm()


def pseudo_electrostatic_packing(im, r, sites=None,
                                 clearance=0,
                                 protrusion=0,
                                 max_iter=1000):
    r"""
    Iterativley inserts spheres as close to the given sites as possible.

    Parameters
    ----------
    im : ndarray
        Imaging containing ``True`` values indicating the phase where
        spheres should be inserted.
    r : int
        Radius of spheres to insert.
    sites : ndarray (optional)
        An image with ``True`` values indicating the electrostatic
        attraction points. If this is not given then the peaks in the
        distance transform are used.
    clearance : int (optional, default=0)
        The amount of space to put between each sphere. Negative values are
        acceptable to create overlaps, but abs(clearance) < r.
    protrusion : int (optional, default=0)
        The amount that spheres are allowed to protrude beyond the active
        phase.
    max_iter : int (optional, default=1000)
        The maximum number of spheres to insert.

    Returns
    -------
    im : ndarray
        Original image overlayed with the inserted spheres.

    """
    dt_im = edt(im)
    if sites is None:
        dt2 = spim.gaussian_filter(dt_im, sigma=0.5)
        strel = ps.tools.ps_round(r, ndim=im.ndim, smooth=True)
        sites = (spim.maximum_filter(dt2, footprint=strel) == dt2)*im
    dt = edt(sites == 0)
    sites = (sites == 0)*(dt_im >= (r-protrusion))
    with tqdm(range(max_iter), **settings.tqdm) as pbar:
        r = r + clearance
        for _ in range(max_iter):
            options = np.where(sites)
            try:
                choice = np.argsort(dt[options])[0]
            except IndexError:
                break
            cen = np.array([options[i][choice] for i in range(im.ndim)])
            im = ps.tools.insert_sphere(im, c=cen, r=r - clearance, v=-1)
            sites = ps.tools.insert_sphere(sites, c=cen, r=2*r, v=0)
            dt = ps.tools.insert_sphere(dt, c=cen, r=r, v=1000)
            pbar.update()
    return im
