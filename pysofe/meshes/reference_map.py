"""
Provides the data structure for the family of reference maps.
"""

# IMPORTS
import numpy as np

from ..elements.simple.lagrange import P1

# DEBUGGING
from IPython import embed as IPS

class ReferenceMap(object):
    """
    Establishes a connection between the reference domain
    and the physical mesh elements.

    Parameters
    ----------

    mesh : pysofe_light.meshes.mesh.Mesh
        The mesh instance
    """

    def __init__(self, mesh):
        self._mesh = mesh

        # currently only supports sraight sided elements
        # hence linear shape element
        self._shape_elem = P1(dimension=mesh.dimension)

    def eval(self, points, deriv=0, mask=None):
        """
        Evaluates each member of the family of reference maps
        or their derivatives at given local points.

        Provides the following forms of information:

        * Zero order information, i.e. the ordinary evaluation, is needed 
          to compute global points given their local counterparts

        * First order information is used to compute Jacobians, e.g. in 
          integral transformations

        Parameters
        ----------

        points : array_like
            The local points at which to evaluate
        
        deriv : int
            The derivation order

        mask : array_like
            Integer or boolean mask specifying certain elements
            of which to evaluate the reference maps

        Returns
        -------
        
        numpy.ndarray
            nE x nP x nD [x nD]
        """

        if points.size == 0:
            # in 1D special case return node coordinates
            # --> nE x (nP) x nD
            return self._mesh.nodes[:,None,:]
        
        points = np.atleast_2d(points)

        # determine topological dimension of the mesh entities
        # onto which to map the given local points
        dim = np.size(points, axis=0)

        # evaluate each basis function of the shape element or
        # their derivatives (according to the order `deriv`) in every point
        basis = self._shape_elem.eval_basis(points, deriv) # nB x nP [x nD[x nD]]

        # get the vertex indices of the mesh entities onto which
        # the reference maps should be evaluated
        vertices = self._mesh.topology.get_entities(d=dim)

        # get the coordinates of all the entities' vertices
        coords = self._mesh.nodes.take(vertices - 1, axis=0)    # nE x nB x nD

        if mask is not None:
            if not isinstance(mask, np.ndarray):
                mask = np.asarray(mask)

            assert mask.ndim == 1

            if mask.dtype == 'int':
                coords = coords.take(mask, axis=0)
            elif mask.dtype == bool:
                coords = coords.compress(mask, axis=0)
            else:
                raise TypeError("Invalue mask type ({})".format(mask.dtype))

        if deriv == 0:
            # basis: nB x nP
            maps = (coords[:,:,None,:] * basis[None,:,:,None]).sum(axis=1)
        elif deriv == 1:
            # basis: nB x nP x nD
            maps = (coords[:,:,None,:,None] * basis[None,:,:,None,:]).sum(axis=1)
        elif deriv == 2:
            # basis: nB x nP x nD x nD
            maps = (coords[:,:,None,:,None,None] * basis[None,:,:,None,:,:]).sum(axis=1)

        return maps

    def eval_inverse(self, points, hosts):
        """
        Evaluates the inverse maps of the reference maps corresponding to the
        given host elements at given global points.

        Parameters
        ----------

        points : array_like
            The global points for which to evaluate the inverse mappings

        hosts : array_like
            The host element for each of the global points
        """

        dim = np.size(points, axis=0)
        
        if not self._shape_elem.order == 1:
            raise ValueError("Inversion only available for linear reference maps!")

        if not self._mesh.dimension in (1, 2):
            raise ValueError("Inversion only available for 1D/2D case")
        else:
            assert dim == self._mesh.dimension

        # if the mesh consists of straight sided cells
        # the reference maps are affine linear and their
        # inversion is simple to calculate
        
        # get coords of first vertex for every cell
        coords = self._mesh.nodes.take(hosts-1, axis=0)
        p0 = coords.take(0, axis=1)
        
        # get edge vectors
        if dim == 1:
            P = coords[:,1] - coords[:,0]
            P_inv = 1./P

            preimages = np.atleast_2d(P_inv * (points.T - p0))
        elif dim == 2:
            p10 = coords[:,1] - coords[:,0]
            p20 = coords[:,2] - coords[:,0]
        
            P = np.dstack([p10, p20])
        
            P_inv = np.linalg.inv(P)
        
            preimages = (P_inv * (points.T - p0)[:,None,:]).sum(axis=-1)

        preimages = preimages.T

        return preimages

    def jacobian_inverse(self, points, mask=None):
        """
        Returns the inverse of the reference maps' jacobians 
        evaluated at given points.

        Parameters
        ----------

        points : array_like
            The local points at which to evaluate the jacobians

        mask : array_like
            Integer or boolean mask specifying certain elements
            of which to evaluate the inverse jacobians
        """

        # evaluate 1st derivative of every reference map
        jacs = self.eval(points=points, deriv=1, mask=mask)

        if jacs.shape[-2:] in {(1,1), (2,2), (3,3)}:
            jacs_inv = np.linalg.inv(jacs)
        elif jacs.shape[-1] == 1:
            jacs_inv = 1./jacs
        else:
            raise NotImplementedError("Jacobian inverse not available yet!")

        return jacs_inv

    def jacobian_determinant(self, points, mask=None):
        """
        Returns the determinants of the reference maps' jacobians 
        evaluated at given points.

        Parameters
        ----------

        points : array_like
            The local points at which to compute the determinants

        mask : array_like
            Integer or boolean mask specifying certain elements
            of which to evaluate the jacobian determinants
        """

        # first we need the jacobians of the reference maps
        # --> nE x nP x nD x nD
        jacs = self.eval(points=points, deriv=1, mask=mask)

        if jacs.shape[-2:] in {(1,1), (2,2), (3,3)}:
            jacs_det = np.linalg.det(jacs)
        elif jacs.shape[-2:] == (2,1):
            jacs_det = np.sqrt(np.power(jacs[...,0], 2).sum(axis=2))
        elif jacs.shape[-2:] == (3,2):
            tmp0 = np.power(jacs[...,1,0] * jacs[...,2,1]
                            - jacs[...,2,0] * jacs[...,1,1], 2)
            tmp1 = np.power(jacs[...,2,0] * jacs[...,0,1]
                            - jacs[...,0,0] * jacs[...,2,1], 2)
            tmp2 = np.power(jacs[...,0,0] * jacs[...,1,1]
                            - jacs[...,1,0] * jacs[...,0,1], 2)
            
            jacs_det = np.sqrt(tmp0 + tmp1 + tmp2)
        else:
            msg = "Unsupported shape of jacobians! ({})"
            raise NotImplementedError(msg.format(jacs.shape))
            #raise NotImplementedError("Jacobian determinant not available yet!")

        return jacs_det
        
