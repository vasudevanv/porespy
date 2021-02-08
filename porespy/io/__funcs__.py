import imageio
import numpy as np
from stl import mesh
import scipy.ndimage as nd
import skimage.measure as ms
from scipy import ndimage as spim
from porespy.tools import sanitize_filename
from porespy.networks import generate_voxel_image
from pyevtk.hl import imageToVTK
import subprocess
import os


def dict_to_vtk(data, filename, voxel_size=1, origin=(0, 0, 0)):
    r"""
    Accepts multiple images as a dictionary and compiles them into a vtk file

    Parameters
    ----------
    data : dict
        A dictionary of *key: value* pairs, where the *key* is the name of the
        scalar property stored in each voxel of the array stored in the
        corresponding *value*.

    path : string
        Path to output file

    voxel_size : int
        The side length of the voxels (voxels  are cubic)

    origin : float
        data origin (according to selected voxel size)

    Notes
    -----
    Outputs a vtk, vtp or vti file that can opened in ParaView

    """
    vs = voxel_size
    for entry in data:
        if data[entry].dtype == bool:
            data[entry] = data[entry].astype(np.int8)
        if data[entry].flags["C_CONTIGUOUS"]:
            data[entry] = np.ascontiguousarray(data[entry])
    imageToVTK(filename, cellData=data, spacing=(vs, vs, vs), origin=origin)


def to_openpnm(net, filename):
    r"""
    Save the result of the `snow` network extraction function in a format
    suitable for opening in OpenPNM.

    Parameters
    ----------
    net : dict
        The dictionary object produced by the network extraction functions

    filename : string or path object
        The name and location to save the file, which will have `.net` file
        extension.

    """
    from openpnm.network import GenericNetwork

    # Convert net dict to an openpnm Network
    pn = GenericNetwork()
    pn.update(net)
    pn.project.save_project(filename)
    ws = pn.project.workspace
    ws.close_project(pn.project)


def to_vtk(im, filename, divide=False, downsample=False, voxel_size=1, vox=False):
    r"""
    Converts an array to a vtk file.

    Parameters
    ----------
    im : 3D image
        The image of the porous material

    path : string
        Path to output file

    divide : bool
        vtk files can get very large, this option allows you for two output
        files, divided at z = half. This allows for large data sets to be
        imaged without loss of information

    downsample : bool
        very large images acan be downsampled to half the size in each
        dimension, this doubles the effective voxel size

    voxel_size : int
        The side length of the voxels (voxels  are cubic)

    vox : bool
        For an image that is binary (1's and 0's) this reduces the file size by
        using int8 format (can also be used to reduce file size when accuracy
        is not necessary ie: just visulization)

    Notes
    -----
    Outputs a vtk, vtp or vti file that can opened in paraview

    """
    if len(im.shape) == 2:
        im = im[:, :, np.newaxis]
    if im.dtype == bool:
        vox = True
    if vox:
        im = im.astype(np.int8)
    vs = voxel_size
    if divide:
        split = np.round(im.shape[2] / 2).astype(np.int)
        im1 = im[:, :, 0:split]
        im2 = im[:, :, split:]
        imageToVTK(
            f"{filename}_1",
            cellData={"im": np.ascontiguousarray(im1)},
            spacing=(vs, vs, vs),
        )
        imageToVTK(
            f"{filename}_2",
            origin=(0.0, 0.0, split * vs),
            cellData={"im": np.ascontiguousarray(im2)},
            spacing=(vs, vs, vs),
        )
    elif downsample:
        im = spim.interpolation.zoom(im, zoom=0.5, order=0, mode="reflect")
        imageToVTK(
            filename,
            cellData={"im": np.ascontiguousarray(im)},
            spacing=(2 * vs, 2 * vs, 2 * vs),
        )
    else:
        imageToVTK(
            filename, cellData={"im": np.ascontiguousarray(im)}, spacing=(vs, vs, vs)
        )


def to_palabos(im, filename, solid=0):
    r"""
    Converts an ND-array image to a text file that Palabos can read in as a
    geometry for Lattice Boltzmann simulations. Uses a Euclidean distance
    transform to identify solid voxels neighboring fluid voxels and labels
    them as the interface.

    Parameters
    ----------
    im : ND-array
        The image of the porous material

    filename : string
        Path to output file

    solid : int
        The value of the solid voxels in the image used to convert image to
        binary with all other voxels assumed to be fluid.

    Notes
    -----
    File produced contains 3 values: 2 = Solid, 1 = Interface, 0 = Pore
    Palabos will run the simulation applying the specified pressure drop from
    x = 0 to x = -1.

    """
    # Create binary image for fluid and solid phases
    bin_im = im == solid
    # Transform to integer for distance transform
    bin_im = bin_im.astype(int)
    # Distance Transform computes Euclidean distance in lattice units to
    # Nearest fluid for every solid voxel
    dt = nd.distance_transform_edt(bin_im)
    dt[dt > np.sqrt(2)] = 2
    dt[(dt > 0) * (dt <= np.sqrt(2))] = 1
    dt = dt.astype(int)
    # Write out data
    with open(filename, "w") as f:
        out_data = dt.flatten().tolist()
        f.write("\n".join(map(repr, out_data)))


def openpnm_to_im(
    network,
    pore_shape="sphere",
    throat_shape="cylinder",
    max_dim=None,
    verbose=1,
    rtol=0.1,
):
    r"""
    Generates voxel image from an OpenPNM network object.

    Parameters
    ----------
    network : OpenPNM GenericNetwork
        Network from which voxel image is to be generated

    pore_shape : str
        Shape of pores in the network, valid choices are "sphere", "cube"

    throat_shape : str
        Shape of throats in the network, valid choices are "cylinder", "cuboid"

    max_dim : int
        Number of voxels in the largest dimension of the network

    rtol : float
        Stopping criteria for finding the smallest voxel image such that
        further increasing the number of voxels in each dimension by 25% would
        improve the predicted porosity of the image by less that ``rtol``

    Returns
    -------
    im : ND-array
        Voxelated image corresponding to the given pore network model

    Notes
    -----
    (1) The generated voxelated image is labeled with 0s, 1s and 2s signifying
    solid phase, pores, and throats respectively.

    (2) If max_dim is not provided, the method calculates it such that the
    further increasing it doesn't change porosity by much.

    """
    return generate_voxel_image(
        network,
        pore_shape=pore_shape,
        throat_shape=throat_shape,
        max_dim=max_dim,
        verbose=verbose,
        rtol=rtol,
    )


def to_stl(im, filename, divide=False, downsample=False, voxel_size=1, vox=False):
    r"""
    Converts an array to an STL file.

    Parameters
    ----------
    im : 3D image
        The image of the porous material

    path : string
        Path to output file

    divide : bool
        vtk files can get very large, this option allows you for two output
        files, divided at z = half. This allows for large data sets to be
        imaged without loss of information

    downsample : bool
        very large images acan be downsampled to half the size in each
        dimension, this doubles the effective voxel size

    voxel_size : int
        The side length of the voxels (voxels  are cubic)

    vox : bool
        For an image that is binary (1's and 0's) this reduces the file size by
        using int8 format (can also be used to reduce file size when accuracy
        is not necessary ie: just visulization)

    Notes
    -----
    Outputs an STL file that can opened in Paraview

    """
    filename = sanitize_filename(filename, ext="stl", exclude_ext=True)
    if len(im.shape) == 2:
        im = im[:, :, np.newaxis]
    if im.dtype == bool:
        vox = True
    if vox:
        im = im.astype(np.int8)
    vs = voxel_size
    if divide:
        split = np.round(im.shape[2] / 2).astype(np.int)
        im1 = im[:, :, 0:split]
        im2 = im[:, :, split:]
        _save_stl(im1, vs, f"{filename}_1")
        _save_stl(im2, vs, f"{filename}_2")
    elif downsample:
        im = spim.interpolation.zoom(im, zoom=0.5, order=0, mode="reflect")
        _save_stl(im, vs * 2, filename)
    else:
        _save_stl(im, vs, filename)


def _save_stl(im, vs, filename):
    r"""
    Helper method to convert an array to an STL file.

    Parameters
    ----------
    im : 3D image
        The image of the porous material

    voxel_size : int
        The side length of the voxels (voxels are cubic)

    filename : string
        Path to output file

    """
    im = np.pad(im, pad_width=10, mode="constant", constant_values=True)
    vertices, faces, norms, values = ms.marching_cubes(im)
    vertices *= vs
    # Export the STL file
    export = mesh.Mesh(np.zeros(faces.shape[0], dtype=mesh.Mesh.dtype))
    for i, f in enumerate(faces):
        for j in range(3):
            export.vectors[i][j] = vertices[f[j], :]
    export.save(f"{filename}.stl")


def to_paraview(im, filename, phase=2):
    r"""
    Converts an array to a paraview state file.

    Parameters
    ----------
    im : ndarray
        The image of the porous material.
    filename : str
        Path to output file.
    phase : str
        The desired phase of output image where phase = 0 represent the
        pore phase, phase = 1 represents the solid phase, and phase= 2 is
        the whole domain. The default value is 2.

    Notes
    -----
    Outputs an pvsm file that can opened in Paraview.

    """
    try:
        import paraview.simple
    except ModuleNotFoundError:
        msg = (
            "The paraview python bindings must be installed using "
            "conda install -c conda-forge paraview, however this may require"
            " using a virtualenv since conflicts with other packages are common."
            " This is why it is not explicitly included as a dependency in"
            " porespy."
        )
        raise ModuleNotFoundError(msg)
    data = im.astype("uint8")
    file = os.path.splitext(filename)[0]
    path = file + ".tiff"
    if len(im.shape) == 2:
        imageio.imwrite(path, np.array(data))
        mode = "2D"
        view = "Slice"
        zshape = 0
        xshape = im.shape[1]
        yshape = im.shape[0]
    elif len(im.shape) == 3:
        imageio.volsave(path, np.array(data))
        mode = "2D"
        view = "Volume"
        zshape = im.shape[0]
        xshape = im.shape[2]
        yshape = im.shape[1]
    maxshape = max(xshape, yshape)
    paraview.simple._DisableFirstRenderCameraReset()
    # create a new 'TIFF Series Reader'
    dtiff = paraview.simple.TIFFSeriesReader(FileNames=[path])
    # get active view
    renderView1 = paraview.simple.GetActiveViewOrCreate("RenderView")
    # uncomment following to set a specific view size
    # renderView1.ViewSize = [1612, 552]
    # get layout
    layout1 = paraview.simple.GetLayout()

    # show data in view
    dtiffDisplay = paraview.simple.Show(dtiff, renderView1, "UniformGridRepresentation")

    # get color transfer function/color map for 'TiffScalars'
    tiffScalarsLUT = paraview.simple.GetColorTransferFunction("TiffScalars")

    # get opacity transfer function/opacity map for 'TiffScalars'
    tiffScalarsPWF = paraview.simple.GetOpacityTransferFunction("TiffScalars")

    # trace defaults for the display properties.
    dtiffDisplay.Representation = view
    dtiffDisplay.ColorArrayName = ["POINTS", "Tiff Scalars"]
    dtiffDisplay.LookupTable = tiffScalarsLUT
    dtiffDisplay.OSPRayScaleArray = "Tiff Scalars"
    dtiffDisplay.OSPRayScaleFunction = "PiecewiseFunction"
    dtiffDisplay.SelectOrientationVectors = "None"
    dtiffDisplay.ScaleFactor = maxshape / 10 - 0.1
    dtiffDisplay.SelectScaleArray = "Tiff Scalars"
    dtiffDisplay.GlyphType = "Arrow"
    dtiffDisplay.GlyphTableIndexArray = "Tiff Scalars"
    dtiffDisplay.GaussianRadius = maxshape / 200 - 0.005
    dtiffDisplay.SetScaleArray = ["POINTS", "Tiff Scalars"]
    dtiffDisplay.ScaleTransferFunction = "PiecewiseFunction"
    dtiffDisplay.OpacityArray = ["POINTS", "Tiff Scalars"]
    dtiffDisplay.OpacityTransferFunction = "PiecewiseFunction"
    dtiffDisplay.DataAxesGrid = "GridAxesRepresentation"
    dtiffDisplay.PolarAxes = "PolarAxesRepresentation"
    dtiffDisplay.ScalarOpacityUnitDistance = 8.256564094912507
    dtiffDisplay.ScalarOpacityFunction = tiffScalarsPWF
    dtiffDisplay.IsosurfaceValues = [0.5]
    dtiffDisplay.SliceFunction = "Plane"

    shape = np.array([xshape, yshape, zshape])

    # init the 'Plane' selected for 'SliceFunction'
    dtiffDisplay.SliceFunction.Origin = [xi / 2 - 0.5 for xi in shape]

    # reset view to fit data
    renderView1.ResetCamera()

    # changing interaction mode based on data extents
    # renderView1.InteractionMode = mode
    renderView1.CameraPosition = [
        xshape / 2 - 0.5,
        yshape / 2 - 0.5,
        4.6 * np.sqrt(np.sum(shape / 2 - 0.5)**2)
    ]
    renderView1.CameraFocalPoint = [xi / 2 - 0.5 for xi in shape]

    # get the material library
    materialLibrary1 = paraview.simple.GetMaterialLibrary()

    # show color bar/color legend
    dtiffDisplay.SetScalarBarVisibility(renderView1, True)

    # update the view to ensure updated data information
    renderView1.Update()

    # saving camera placements for all active views
    # current camera placement for renderView1
    # renderView1.InteractionMode = mode
    renderView1.CameraPosition = [
        xshape / 2 - 0.5,
        yshape / 2 - 0.5,
        4.6 * np.sqrt(np.sum(shape / 2 - 0.5)**2)
    ]
    renderView1.CameraFocalPoint = [xi / 2 - 0.5 for xi in shape]
    renderView1.CameraParallelScale = np.sqrt(np.sum(shape / 2 - 0.5)**2)

    # uncomment the following to render all views
    # RenderAllViews()
    # alternatively, if you want to write images, you can use SaveScreenshot(...).
    threshold1 = paraview.simple.Threshold(Input=dtiff)
    threshold1.Scalars = ["POINTS", "Tiff Scalars"]
    if phase == 0:
        range = [0.5, 1]
    elif phase == 1:
        range = [0, 0.5]
    else:
        range = [0, 1]
    threshold1.ThresholdRange = range

    # show data in view
    threshold1Display = paraview.simple.Show(threshold1, renderView1,
                                             "UnstructuredGridRepresentation")

    # hide data in view
    paraview.simple.Hide(dtiff, renderView1)

    paraview.simple.SaveState(file + ".pvsm")


def open_paraview(filename=None, im=None, **kwargs):
    r"""
    Open a paraview state file or image directly in paraview.

    Parameters
    ----------
    filename : str
        Path to input state file.
    im : ND-array
        An image to open directly.  If no filename given, then this image is
        sent to ``to_paraview`` and a state file is created with a random name.
        Any additional keyword arguments are sent to ``to_paraview``.

    """
    if filename is None:
        import uuid
        filename = str(uuid.uuid4())[:8]
        to_paraview(im=im, filename=filename, **kwargs)
    file = os.path.splitext(filename)[0]
    statefile = file + ".pvsm"
    # paraview_path = "paraview.exe"
    paraview_path = "paraview"
    subprocess.Popen([paraview_path, statefile])
