import pytest
import numpy as np
from edt import edt
import porespy as ps
import scipy.ndimage as spim
from skimage.morphology import disk, ball, skeletonize_3d, square


class IBIPTest():
    def setup_class(self):
        im = ps.generators.lattice_spheres(shape=[107, 107],
                                           radius=5, offset=9,
                                           lattice='tri')
        self.im = im[5:102, 5:102]
        bd = np.zeros_like(self.im)
        bd[:, 0] = True
        self.bd = bd

    def sc_lattice_with_trapped_region(self):
        im = np.copy(self.im)
        crds = ps.generators.line_segment([64, 64], [49, 80])
        im[tuple(crds)] = False
        crds = ps.generators.line_segment([30, 64], [49, 80])
        im[tuple(crds)] = False
        im = ~spim.binary_dilation(~im, structure=square(3))
        return im

    def test_ibip(self):
        inv = ps.filters.ibip(self.im, inlets=self.bd)
        assert inv.max() == 119

    def test_ibip_w_trapping(self):
        im = self.sc_lattice_with_trapped_region()
        inv = ps.filters.ibip(im, inlets=self.bd)
        assert inv.max() == 153
        inv_w_trapping = ps.filters.find_trapped_regions(seq=inv,
                                                         return_mask=True)
        assert inv_w_trapping.sum() == 390
        inv_w_trapping = ps.filters.find_trapped_regions(seq=inv,
                                                         return_mask=False)
        assert (inv_w_trapping == -1).sum() == 390

    def test_mio_w_trapping(self):
        np.random.seed(0)
        im = ps.generators.overlapping_spheres(shape=[100, 100],
                                               radius=6, porosity=0.6)
        bd = np.zeros_like(im)
        bd[:, 0] = True
        inv = ps.filters.porosimetry(im, inlets=bd)
        seq = ps.tools.size_to_seq(inv)
        inv_w_trapping = ps.filters.find_trapped_regions(seq=seq,
                                                         return_mask=False)
        assert (inv_w_trapping == -1).sum() == 236


if __name__ == '__main__':
    t = IBIPTest()
    self = t
    t.setup_class()
    for item in t.__dir__():
        if item.startswith('test'):
            print('running test: '+item)
            t.__getattribute__(item)()