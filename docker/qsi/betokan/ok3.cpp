
/*  BET - Brain Extraction Tool

    BETv1 Steve Smith
    BETv2 Mickael Pechaud, Mark Jenkinson, Steve Smith
    FMRIB Image Analysis Group

    Copyright (C) 1999-2006 University of Oxford  */

/*  CCOPYRIGHT  */

/*  Changes from FSL's bet2.cpp (fsl/bet2 tag 2111.9), distributed under the
    FSL licence like the original:

    TORTOISE links a prebuilt x86-64 archive, libbetokan.a, whose object ok3.o
    is bet2.cpp with main() turned into mainokan(), taking the volume as arrays
    instead of file names. This file rebuilds that entry point from FSL's
    source, so that TORTOISE also links on other processors.

    - main() is mainokan(argc, argv) with TORTOISE's convention
      (external_libraries/bet/Linux/betokan.h): argv[0] is int[3] sizes,
      argv[1] float[3] voxel sizes in mm, argv[2] the float image (x fastest),
      argv[3] the caller's float output, same size; then "-f" followed by a
      pointer to a float (not a string), and "-v".
    - The output is the brain image bet2 saves by default, the input inside
      the brain and 0 outside, in the input's voxel order; TORTOISE takes its
      nonzero voxels as the mask. The original ok3.o writes the same: on the
      volumes tested its output is identical to this, voxel for voxel.
    - Nothing is printed: the original ignores "-v", so this does too.
    - The option parser is gone: every other option keeps bet2's default, and
      the code only bet2's other outputs use (outline, skull, mesh, CT, -t,
      -c, --binaryMask) is removed. The remaining functions are copied
      unchanged, in an anonymous namespace so their names cannot clash with
      the program that links them.  */

#include <cmath>
#include <iostream>
#include <list>
#include <vector>
#include <algorithm>
#include <cstring>

#include "miscmaths/miscmaths.h"
#include "newimage/newimageall.h"
#include "meshclass/meshclass.h"

using namespace std;
using namespace MISCMATHS;
using namespace NEWIMAGE;
using namespace mesh;

namespace {

struct bet_parameters
{
  double min, max, t98, t2, t, tm, radius;
  //Ellipsoid radii not used for now
  double radiusX, radiusY, radiusZ;
  Pt cog;
};

const double normal_max_update_fraction = .5;
const double lambda_fit = .1;

// bet2's option defaults, other than -f and -v which TORTOISE passes.
const float gradient_threshold = 0.0;  // -g
const float smootharg = 1.0;           // -w
const float radiusarg = 0.0;           // -r
const float d1 = 7.0;                  // --parameter_d1
const float d2 = 3.0;                  // --parameter_d2


void draw_segment(volume<short>& image, const Pt& p1, const Pt& p2)
{
  double xdim = (double) image.xdim();
  double ydim = (double) image.ydim();
  double zdim = (double) image.zdim();
  double mininc = min(xdim,min(ydim,zdim)) * .5;

  Vec n = p1 - p2;
  double d = n.norm();
  n.normalize();

  for (double i=0; i<=d; i+=mininc)
    {
      Pt p = p2 + i* n;
      image((int) floor((p.X)/xdim +.5),(int) floor((p.Y)/ydim +.5),(int) floor((p.Z)/zdim +.5)) = 0;
    }
}


volume<short> draw_mesh(const volume<short>& image, const Mesh &m)
{
  double xdim = (double) image.xdim();
  double ydim = (double) image.ydim();
  double zdim = (double) image.zdim();
  double mininc = min(xdim,min(ydim,zdim)) * .5;
  volume<short> res = image;
  for (list<Triangle*>::const_iterator i = m._triangles.begin(); i!=m._triangles.end(); i++)
    {
      Vec n = (*(*i)->get_vertice(0) - *(*i)->get_vertice(1));
      double d = n.norm();
      n.normalize();

      for (double j=0; j<=d; j+=mininc)
	{
	  Pt p = (*i)->get_vertice(1)->get_coord()  + j* n;
	  draw_segment(res, p, (*i)->get_vertice(2)->get_coord());
	}
    }
  return res;
}


//calculates the mask from the mesh by spreading an initial point outside the mesh, and stopping it when the mesh is reached.
volume<short> make_mask_from_mesh(const volume<float> & image, const Mesh& m)
{
  double xdim = (double) image.xdim();
  double ydim = (double) image.ydim();
  double zdim = (double) image.zdim();

  volume<short> mask;
  copyconvert(image,mask);

  int xsize = mask.xsize();
  int ysize = mask.ysize();
  int zsize = mask.zsize();

  mask = 1;

  mask = draw_mesh(mask, m);

  vector<Pt> current;
  current.clear();
  Pt c(0., 0., 0.);
  for (vector<Mpoint *>::const_iterator it=m._points.begin(); it!=m._points.end(); it++)
    c+=(*it)->get_coord();

  c*=(1./m._points.size());
  c.X/=xdim; c.Y/=ydim; c.Z/=zdim;

  current.push_back(c);

  while (!current.empty())
    {
      Pt pc = current.back();
      int x, y, z;
      x=(int) pc.X; y=(int) pc.Y; z=(int) pc.Z;
      current.pop_back();
      mask.value(x, y, z) = 0;
      if (0<=x-1 && mask.value(x-1, y, z)==1) current.push_back(Pt(x-1, y, z));
      if (0<=y-1 && mask.value(x, y-1, z)==1) current.push_back(Pt(x, y-1, z));
      if (0<=z-1 && mask.value(x, y, z-1)==1) current.push_back(Pt(x, y, z-1));
      if (xsize>x+1 && mask.value(x+1, y, z)==1) current.push_back(Pt(x+1, y, z));
      if (ysize>y+1 && mask.value(x, y+1, z)==1) current.push_back(Pt(x, y+1, z));
      if (zsize>z+1 && mask.value(x, y, z+1)==1) current.push_back(Pt(x, y, z+1));
    }

  return mask;
}


bool withinLimits(bet_parameters bp, const Pt& p, const Pt& c) {
    return (((p - c)|(p - c)) < ( bp.radius * bp.radius ) );
}

bet_parameters adjust_initial_mesh(const volume<float> & image, Mesh& m, const double & rad = 0., const double xpara=0.,  const double ypara=0.,  const double zpara=0.)
{
  bet_parameters bp;
  double t2, t98, t;

  //computing t2 && t98

  bp.min = image.min();
  bp.max = image.max();

  t2 = image.robustmin();
  t98 = image.robustmax();

  t = t2 + .1*(t98 - t2);
  bp.t98 = t98;
  bp.t2 = t2;
  bp.t = t;

  if (rad == 0.)
    {
      double radius=0;
      int64_t counter(0);
      for (int k=0; k<image.zsize(); k++)
	for (int j=0; j<image.ysize(); j++)
	  for (int i=0; i<image.xsize(); i++)
	    {
	      double c = image(i, j, k);
	      if (c > t)
		{
		  counter+=1;
		}
	    }
      //Initial guess for radius, assuming the sphere can fit in the FOV
      radius = pow (.75 * counter*image.xdim()*image.ydim()*image.zdim()/M_PI, 1.0/3.0);
      short dimensionality(3);

      if ( image.xsize() * image.xdim() < radius ) {
        radius = pow (counter*image.ydim()*image.zdim()/M_PI/image.xsize(), 1.0/2.0);
        dimensionality--;
      }
      if ( image.ysize() * image.ydim() < radius ) {
        radius = pow (counter*image.xdim()*image.zdim()/M_PI/image.ysize(), 1.0/2.0);
        dimensionality--;
      }
      if ( image.zsize() * image.zdim() < radius ) {
        radius = pow (counter*image.xdim()*image.ydim()/M_PI/image.zsize(), 1.0/2.0);
        dimensionality--;
      }
      if ( dimensionality < 2 )
        cerr << "Warning: Image appears to be 1D" << endl;

      bp.radius = radius;
    }
    else (bp.radius = rad);

  //Ellispoid radii, currently unused
  bp.radiusX = ( image.xsize() * image.xdim() > bp.radius  ) ? bp.radius : image.xdim();
  bp.radiusY = ( image.ysize() * image.ydim() > bp.radius  ) ? bp.radius : image.ydim();
  bp.radiusZ = ( image.zsize() * image.zdim() > bp.radius  ) ? bp.radius : image.zdim();



  //finds the COG
  Pt center(0, 0, 0);
  if (xpara == 0. & ypara==0. & zpara==0.)
    {
      double counter(0); //This should be int64_t, but double here to preserve old results for now
      double tmp = t - t2;
      for (int k=0; k<image.zsize(); k++)
	      for (int j=0; j<image.ysize(); j++)
	        for (int i=0; i<image.xsize(); i++) {
	          double c = image(i, j, k ) - t2;
	          if (c > tmp) {
		          c = min(c, t98 - t2);
		          counter+=c;
		          center +=  Pt(c*i*image.xdim(), c*j*image.ydim(), c*k*image.zdim());
		        }
	        }
      center=Pt(center.X/counter, center.Y/counter, center.Z/counter);
    }
  else center=Pt(xpara*image.xdim(), ypara*image.ydim(), zpara*image.zdim());

  bp.cog = center;

  m.translation(center.X, center.Y, center.Z);
  m.rescale(bp.radius/2.0,center);

  //computing tm
  vector<double> vm;
  for (int k=0; k<image.zsize(); k++)
    for (int j=0; j<image.ysize(); j++)
      for (int i=0; i<image.xsize(); i++)
	{
	  double d = image.value(i, j, k);
	  Pt p(i*image.xdim(), j*image.ydim(), k*image.zdim());
	  if (d > t2 && d < t98 && withinLimits(bp,p,center) ) {
	    vm.push_back(d);
    }
	}

  //For an input such as a binary mask, vm will be empty due to the < t98 test above
  //Safe option here is to set the median to the robust max
  if ( !vm.empty() ) {
    int med = (int) floor(vm.size()/2.);
    nth_element(vm.begin(), vm.begin() + med - 1, vm.end());
    double tm=(*max_element(vm.begin(), vm.begin() + med));
    bp.tm = tm;
  } else {
    bp.tm=bp.t98;
  }

  return bp;
}



double step_of_computation(const volume<float> & image, Mesh & m, const double bet_main_parameter, const int pass, const double increase_smoothing, const int iteration_number, double & l, const double t2, const double tm, const double t, const double E,const double F, const double zcog, const double radius, const double local_th=0., const int d1=7, const int d2=3){
  double xdim = ( image.xsize()*image.xdim() > radius ) ? image.xdim() : 2.0*radius;
  double ydim = ( image.ysize()*image.ydim() > radius ) ? image.ydim() : 2.0*radius;
  double zdim = ( image.zsize()*image.zdim() > radius ) ? image.zdim() : 2.0*radius;
  double dscale = Min(Min(Min(xdim,ydim),zdim),1.0);

  if (iteration_number==50 || iteration_number%100 == 0 )
    {
      l = 0;
      int counter = 0;
      for (vector<Mpoint*>::iterator i = m._points.begin(); i!=m._points.end(); i++ )
	{
	  counter++;
	  l += (*i)->medium_distance_of_neighbours();
	}
      l/=counter;
    }

  for (vector<Mpoint*>::iterator i = m._points.begin(); i!=m._points.end(); i++)
    {
      Vec sn, st, u1, u2, u3, u;
      double f2, f3=0;

      Vec n = (*i)->local_normal();
      Vec dv = (*i)->difference_vector();

      double tmp = dv|n;
      sn = n * tmp;
      st = dv - sn;

      u1 = st*.5;

      double rinv = (2 * fabs(sn|n))/(l*l);

      f2 = (1+tanh(F*(rinv - E)))*0.5;
      if (pass > 0)
	if (tmp > 0) {
	  f2*=increase_smoothing;
	  f2 = Min(f2, 1.);
	}

      u2 = f2 * sn;

      //main term of bet
      {
	double local_t = bet_main_parameter;
	if (local_th != 0.0)
	  {
	    local_t = Min(1., Max(0., bet_main_parameter + local_th*((*i)->get_coord().Z - zcog)/radius));
	  }

	double Imin = tm;
	double Imax = t;

	Pt p = (*i)->get_coord() + (-1)*n;
	double iv = p.X/xdim + .5, jv = p.Y/ydim +.5, kv = p.Z/zdim +.5;
	if (image.in_bounds((int)iv,(int) jv,(int) kv))
	  {
	    double im=image.value((int)iv,(int)jv,(int)kv);
	    Imin = Min(Imin, im);
	    Imax = Max(Imax,im);

	    double nxv=n.X/xdim, nyv=n.Y/ydim, nzv=n.Z/zdim;
	    int i2=(int)(iv-(d1-1)*nxv), j2 =(int) (jv-(d1-1)*nyv), k2 =(int)(kv-(d1-1)*nzv);
	    nxv*=dscale; nyv*=dscale; nzv*=dscale;
	    if (image.in_bounds(i2, j2, k2))
	      {
		im=image.value(i2,j2,k2);
		Imin = Min(Imin, im);

		for (double gi=2.0; gi<d1; gi+=dscale)
		  {
		    // the following is a quick calc of Pt p = (*i)->get_coord() + (-gi)*n;
		    iv-=nxv; jv-=nyv; kv-=nzv;
		    im = image.value((int) (iv), (int) (jv), (int) (kv));
		    Imin = Min(Imin, im);

		    if (gi<d2)
		      Imax = Max(Imax,im);
		  }

		Imin = Max (t2, Imin);
		Imax = Min (tm, Imax);

		const double tl = (Imax - t2) * local_t + t2;

		if (Imax - t2 > 0)
		  f3=2*(Imin - tl)/(Imax - t2);
		else f3=(Imin - tl)*2;
	      }
	  }

      }

      f3 *= (normal_max_update_fraction * lambda_fit * l);

      u3 = f3 * n;

      u = u1 + u2 + u3;

      (*i)->_update_coord = (*i)->get_coord() + u;
    }

  m.update();

  return (0);
}

}  // namespace


int mainokan(int argc, char *argv[]) {

  const int *sizes = (const int *) argv[0];
  const float *res = (const float *) argv[1];
  const float *in = (const float *) argv[2];
  float *out = (float *) argv[3];

  float fractional_threshold = 0.5;
  for (int a = 4; a + 1 < argc; a++)
    if (!strcmp(argv[a], "-f")) fractional_threshold = *(const float *) argv[++a];

  if (fractional_threshold < 0 || fractional_threshold > 1) {
    cerr << endl << "Fractional intensity threshold must be between 0 and 1!" << endl;
    return -1;
  }

  // In place of read_volume: the caller's voxel order and voxel sizes. With
  // no orientation given, nothing is mirrored, whereas read_volume mirrors x
  // of a neurological image (positive determinant) into FSL's radiological
  // order; so did the original, which also had no orientation to go by.
  const int xsize = sizes[0], ysize = sizes[1], zsize = sizes[2];
  volume<float> testvol(xsize, ysize, zsize);
  testvol.setdims(res[0], res[1], res[2]);
  for (int k=0; k<zsize; k++)
    for (int j=0; j<ysize; j++)
      for (int i=0; i<xsize; i++)
	testvol.value(i, j, k) = in[i + (size_t) xsize * (j + (size_t) ysize * k)];

  const double xarg = 0, yarg = 0, zarg = 0;

  const double bet_main_parameter = pow(fractional_threshold, .275);

  Mesh m;
  make_mesh_from_icosa(5, m);


  bet_parameters bp = adjust_initial_mesh(testvol, m, radiusarg, xarg, yarg, zarg);

  Mesh moriginal=m;

  const double rmin=3.33 * smootharg;
  const double rmax=10 * smootharg;
  const double E = (1/rmin + 1/rmax)/2.;
  const double F = 6./(1/rmin - 1/rmax);
  const int nb_iter = 1000;
  const double self_intersection_threshold = 4000;

  double l = 0;
  for (int i=0; i<nb_iter; i++)
    {
      step_of_computation(testvol, m, bet_main_parameter, 0, 0, i, l, bp.t2, bp.tm, bp.t, E, F, bp.cog.Z, bp.radius, gradient_threshold,d1,d2);
    }

  double tmp = m.self_intersection(moriginal);
  bool self_intersection = (tmp > self_intersection_threshold);
  int pass = 0;

  //self-intersection treatment
  while (self_intersection)
    {
      m = moriginal;
      l = 0;
      pass++;
      for (int i=0; i<nb_iter; i++)
	{
	  double incfactor = pow (10.0,(double) pass + 1);
	  if (i > .75 * (double)nb_iter)
	    incfactor = 4.*(1. - i/(double)nb_iter) * (incfactor - 1.) + 1.;
	  step_of_computation(testvol, m, bet_main_parameter, pass, incfactor, i, l, bp.t2, bp.tm, bp.t, E, F, bp.cog.Z, bp.radius, gradient_threshold,d1,d2);
	}
      double tmp = m.self_intersection(moriginal);

      self_intersection = (tmp > self_intersection_threshold);

      if (pass==10) // give up
	self_intersection=0;
    }

  volume<short> brainmask = make_mask_from_mesh(testvol, m);

  // bet2's default output, the segmented brain image.
  for (int k=0; k<zsize; k++)
    for (int j=0; j<ysize; j++)
      for (int i=0; i<xsize; i++)
	out[i + (size_t) xsize * (j + (size_t) ysize * k)] = (1-brainmask.value(i, j, k)) * testvol.value(i, j, k);

  return 0;
}
